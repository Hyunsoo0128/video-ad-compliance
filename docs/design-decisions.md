# Design Decisions Document (Architecture Decision Record)
# Ad Compliance Automation Pipeline

**Target Audience**: Developers who will implement and maintain this system  
**Purpose**: Explains the "why" behind the design in architecture.md  
**Version**: 1.0 | 2026-03-24

---

## Table of Contents

1. [Overview: Purpose of This Document](#1-overview)
2. [ADR-001: Why TwelveLabs](#2-adr-001-why-twelvelabs)
3. [ADR-002: Why a 2-Phase Pipeline](#3-adr-002-why-a-2-phase-pipeline)
4. [ADR-003: Why Register Two Models Simultaneously for Indexing](#4-adr-003-why-register-two-models-simultaneously-for-indexing)
5. [ADR-004: Why Consolidate Policy Analysis into a Single Call](#5-adr-004-why-consolidate-policy-analysis-into-a-single-call)
6. [ADR-005: Why Enforce JSON Schema](#6-adr-005-why-enforce-json-schema)
7. [ADR-006: Why Multi-Signal Scoring](#7-adr-006-why-multi-signal-scoring)
8. [ADR-007: Why Confidence-Based Hybrid Review](#8-adr-007-why-confidence-based-hybrid-review)
9. [ADR-008: Why SQS + ECS Architecture](#9-adr-008-why-sqs--ecs-architecture)
10. [API Behavior Detailed Guide](#10-api-behavior-detailed-guide)
11. [Threshold Configuration Rationale](#11-threshold-configuration-rationale)
12. [Known Limitations and Trade-offs](#12-known-limitations-and-trade-offs)
13. [Implementation Notes](#13-implementation-notes)

---

## 1. Overview

architecture.md describes **what** we build. This document describes **why** we build it that way.

Each design decision is written in ADR (Architecture Decision Record) format, following this structure:

- **Context**: The situation that required a decision
- **Options**: Alternatives considered
- **Decision**: Final choice and rationale
- **Consequences**: Trade-offs resulting from this decision

---

## 2. ADR-001: Why TwelveLabs

### Context

Video ad compliance analysis requires multimodal capabilities that **simultaneously** understand visual, audio, and on-screen text. The options reviewed as of March 2026 are as follows.

### Options

| Option | Pros | Cons |
|---|---|---|
| **A. TwelveLabs (Marengo + Pegasus)** | Video-native model, JSON Schema enforcement, embedding+generation unified | Relatively high cost |
| B. Google Gemini | General-purpose multimodal, long context | Unstable structured output, cost ~$10.62/min (~4x Pegasus) |
| C. AWS Nova | Low cost (~$0.22/min) | Difficult structured output control, lower accuracy |
| D. Custom pipeline (Whisper + CLIP + LLM) | Full control | Extremely high integration complexity, no temporal reasoning, maintenance burden |

### Decision: A. TwelveLabs

**Key Rationale:**

1. **Video-native**: Gemini and GPT-4V are frame-sampling based, but TwelveLabs understands the video stream itself. **Temporal action reasoning** like "applying lip tint to the eye at 01:23" is only possible with video-native models.

2. **Role-separated architecture**: Marengo (embedding/search) and Pegasus (generation/reasoning) are separated, naturally enabling a 2-phase pipeline: low-cost search filtering → expensive analysis only on qualifying videos. Gemini cannot provide this separation.

3. **JSON Schema enforcement**: Output schema can be enforced via prompt-embedded schema instructions, producing reliable structured results. (Note: `response_format` mode was found to suppress audio-based violation detection; see ADR-005.)

4. **Bedrock integration**: Both Marengo 3.0 and Pegasus 1.2 are available on Amazon Bedrock, facilitating future infrastructure-level caching and integration with existing AWS workloads.

### Consequences

- (+) Single vendor covers embedding through generation → minimized integration complexity
- (+) 2-phase pipeline enables cost optimization
- (-) Vendor dependency on TwelveLabs API
- (-) Risk of full pipeline halt on API outage → mitigated with DLQ + graceful degradation

---

## 3. ADR-002: Why a 2-Phase Pipeline

### Context

Calling Pegasus Analyze on every video is accurate but expensive. A significant portion of submitted videos may be unrelated to the campaign (gaming streams, mukbang, etc.).

### Options

| Option | Cost | Accuracy |
|---|---|---|
| A. Run Pegasus Analyze on all videos directly | High (100% Pegasus calls) | High |
| **B. Filter with Embed-based cosine similarity → Pegasus only on passing videos** | Low (15~25% savings) | Same (off-brief videos would be BLOCKed anyway) |
| C. Metadata-based filtering (title, tags) | Very low | Low (creators may tag incorrectly) |

### Decision: B. 2-Phase Pipeline

```
Phase 1: Retrieve pre-indexed embeddings + text embedding + cosine similarity (low cost, fast)
  "Is this video related to the beauty campaign?"
  → score < 0.3 → immediate BLOCK → skip Phase 2

Phase 2: Pegasus Analyze (high cost, precise)
  "Does this video contain policy violations?"
  → Only analyzes videos that passed Phase 1
```

**Key Rationale:**

- Phase 1 retrieves already-indexed segment embeddings and computes cosine similarity locally, so additional cost is very low
- Off-brief videos would be BLOCKed anyway, making policy violation analysis unnecessary
- An estimated 15~25% of submissions in real creator campaigns are unrelated content

### Consequences

- (+) 15~25% reduction in Pegasus calls → cost savings on the second most expensive step after indexing
- (+) Fast feedback for off-brief videos (decision completed with Phase 1 alone)
- (-) If the Phase 1 score threshold (0.3) is misconfigured, legitimate videos may be BLOCKed → mitigated by treating all BLOCKs as REVIEW during the first 2 weeks for validation

---

## 4. ADR-003: Why Register Two Models Simultaneously for Indexing

### Context

When creating a TwelveLabs index, we must decide whether to register only Marengo or both Marengo and Pegasus.

### Decision: Register Both Models Simultaneously

```python
models=[
    IndexesCreateRequestModelsItem(model_name="marengo3.0", ...),
    IndexesCreateRequestModelsItem(model_name="pegasus1.2", ...)
]
```

**Key Rationale:**

1. **Cannot add models after index creation**: This is a structural constraint of the TwelveLabs API. Adding Pegasus later requires creating a new index and re-indexing all videos.

2. **Indexing accounts for ~60% of total cost**: Indexing separately per model doubles the cost. Enabling both models with a single indexing pass is key to cost optimization.

3. **Clear role separation**:
   - Marengo: Embedding generation + semantic search (`search.query()`, `embed.create()`)
   - Pegasus: Video-based text generation + reasoning (`analyze()`)
   - Embeddings are handled by Marengo only; generation by Pegasus only. No cross-usage.

### Notes

- Both `visual` and `audio` modalities must be enabled
- In v1.3, the former `conversation`, `text_in_video`, `logo`, etc. have been consolidated into `visual`/`audio`
- Modality settings also cannot be changed without deleting and recreating the index

---

## 5. ADR-004: Why Consolidate Policy Analysis into a Single Call

### Context

When analyzing 5 policy categories (hate, profanity, drugs, unsafe use, medical claims), we must decide whether to call separately per category or consolidate into one call.

### Options

| Option | Cost | Accuracy | Implementation Complexity |
|---|---|---|---|
| A. 5 separate calls per category | 5x | Potentially slightly higher | High (merging 5 results) |
| **B. Single call + unified JSON Schema** | 1x | Sufficiently high | Low |
| C. 1 base call + re-analyze only suspicious categories | 1x ~ 2x | Highest | Medium |

### Decision: B (default) + C (future enhancement)

**Rationale for single call as default:**

1. **Nature of video analysis**: Pegasus re-watches the entire video from start to finish on each call. 5 calls means watching the same video 5 times. Unlike text LLMs, prompt length is not the bottleneck — watching the video itself accounts for most of the cost.

2. **Benefit of shared context**: "At 01:23, applying lip tint to the eye while saying 'it clears up blemishes'" → `UNSAFE_PRODUCT_USE` + `MEDICAL_CLAIMS` triggered simultaneously. A consolidated call captures this correlation better. Separate calls judge independently and may miss this context.

3. **5x cost difference**: The most direct reason.

**Adding approach C for future enhancement:**

After operational stabilization, re-analyze only categories where MEDIUM or higher violations are detected, using category-specific prompts. This corresponds to the "Pegasus re-analysis of inconsistent segments" in architecture.md section 10.4.

### Consequences

- (+) 80% cost reduction (5 calls → 1 call)
- (+) Cross-category context sharing
- (-) Longer prompts may degrade judgment quality for some categories → mitigated by enum constraints in prompt-embedded schema
- (-) Single call failure means entire analysis fails → retry logic required

---

## 6. ADR-005: Why Enforce JSON Schema

### Context

Pegasus Analyze output must be parsed in the automation pipeline. Free-text output carries parsing failure risk.

### Decision: Embed JSON Schema in prompt text

Originally we used `response_format=ResponseFormat(type="json_schema", ...)` for guaranteed structured output. However, testing revealed that this mode causes Pegasus 1.2 to **suppress audio-based violation detection** — spoken profanity and medical claims were ignored even though the model could transcribe them correctly in free-form mode.

The schema is now embedded directly in the prompt text:

```python
schema_hint = (
    "\n\nYou MUST respond with a JSON object matching this schema:\n"
    + json.dumps(ANALYSIS_SCHEMA, indent=2)
)

result = client.analyze(
    video_id=video_id,
    prompt=COMPLIANCE_PROMPT + schema_hint,
)
```

**Key Rationale:**

1. **Full multimodal analysis**: Preserves audio-based violation detection that `response_format` mode suppresses
2. **Enum constraints**: Schema in prompt still restricts categories and severities via explicit instruction
3. **Downstream stability**: Decision Engine, evidence reports, and dashboards all depend on a fixed schema
4. **Reliable JSON output**: Pegasus consistently returns valid JSON when instructed via prompt; retry logic handles rare parse failures

### Trade-offs

- (-) Slightly higher parse failure risk than `response_format` enforcement (mitigated by retry logic)
- (-) Schema changes require updating the prompt
- (+) Audio violations (profanity, medical claims) are now correctly detected
- Resolution: Monitor parse failure rate; revert to `response_format` if Pegasus SDK fixes the audio suppression issue

---

## 7. ADR-006: Why Multi-Signal Scoring

### Context

The base pipeline relies on only two signals: Marengo score and Pegasus severity. If the model is wrong, there is no means of correction.

### Problem Scenario

```
Scenario: Creator says "this foundation is insane"
  → Pegasus judges PROFANITY: HIGH (false positive)
  → Base pipeline: BLOCK as-is
  → Multi-Signal: Marengo Search identifies it as normal beauty content (score 0.85)
     → Signal inconsistency detected → confidence downgraded → switched to REVIEW
     → Manual reviewer confirms false positive → APPROVE
```

### Decision: 5-Signal Ensemble (Phased Rollout)

| Phase | Signal | Timing |
|---|---|---|
| Immediate | ① Marengo Search score | Day 1 |
| Immediate | ② Pegasus Analyze severity | Day 1 |
| Immediate | ③ Embedding cosine similarity | Day 1 |
| After 2 weeks | ④ Platt Scaling calibration | After manual review data accumulation |
| After 1 month | ⑤ Cross-modal consistency | After Embed API integration |

**Key Rationale:**

- A single model's confidence of 0.7 does not mean 70% actual accuracy → calibration needed
- When visual and audio contradict (applying lipstick while saying "eyeliner") → cross-modal verification needed
- High agreement across signals → HIGH CONFIDENCE → auto-process; disagreement → LOW CONFIDENCE → manual review

### Consequences

- (+) Other signals correct single-model misjudgments
- (+) Confidence tiers (HIGH/MEDIUM/LOW) expand auto-processing scope
- (-) Increased implementation complexity → mitigated by phased rollout
- (-) Additional API calls (Embed API) → only during cross-modal verification, minimal cost increase

---

## 8. ADR-007: Why Confidence-Based Hybrid Review

### Context

Since AI cannot be 100% accurate, we must decide what to auto-process and where humans intervene.

### Options

| Option | Automation Rate | Risk |
|---|---|---|
| A. Full manual review (AI as assistant) | 0% | No cost savings |
| B. Full auto-processing | 100% | False positive/negative risk |
| **C. Confidence-based routing** | 70~80% | Balanced |

### Decision: C. Confidence-Based 3-Tier Routing

```
confidence ≥ 0.9  →  Auto-process (no human intervention)
0.6 ≤ conf < 0.9  →  REVIEW queue (reviewer judges with AI results)
confidence < 0.6  →  Priority REVIEW + senior escalation
```

**Key Rationale:**

- 0.9 threshold: Auto-process only when "correct more than 9 out of 10 times." Ad compliance carries higher risk from false negatives than false positives, so this is set conservatively
- AI results in REVIEW queue: Manual reviewers don't judge from scratch — AI indicates "there's an issue at 01:23," so they only check that segment → drastically reduced review time
- Feedback loop: Manual review results accumulate as calibration training data → auto-processing rate increases over time

### Consequences

- (+) 70~80% auto-processing → up to 90% reduction in manual review costs
- (+) False positives are caught in manual review → safety net
- (+) Continuous improvement via feedback loop
- (-) Low auto-processing rate during the first 2 weeks (conservative operation before calibration)

---

## 9. ADR-008: Why SQS + ECS Architecture

### Context

TwelveLabs indexing is an asynchronous operation (tens of seconds to minutes), and we need to process 10,000 items per day.

### Options

| Option | Pros | Cons |
|---|---|---|
| A. Direct Lambda invocation | Serverless, simple | 15-min timeout, wasted cost during indexing wait |
| **B. SQS (FIFO) + ECS Fargate** | Deduplication, long-running tasks, auto-scaling | Slight infrastructure management needed |
| C. Step Functions | Workflow visualization | Over-engineering, unnecessary for a simple pipeline |

### Decision: B. SQS FIFO + ECS Fargate

**Key Rationale:**

1. **Indexing wait**: TwelveLabs indexing takes 30s~5min depending on video length. Within Lambda's 15-min limit, but billed during wait time. ECS handles polling/webhook waiting naturally
2. **FIFO queue**: Prevents duplicate submission of the same video (using video_id as MessageDeduplicationId)
3. **Auto-scaling**: ECS task count auto-adjusts based on SQS queue depth. Workers increase at peak, scale down when idle
4. **DLQ**: On API failures or repeated errors, messages move to Dead Letter Queue → automatic transition to manual review queue

### TwelveLabs API Rate Limit Handling

```
Worker-level semaphore (concurrent request limit)
  → Exponential backoff on 429 response (2s → 4s → 8s → 16s + jitter)
  → Monitor X-RateLimit-Remaining header
  → Move to DLQ after 5 consecutive failures
```

---

## 10. API Behavior Detailed Guide

This section describes the actual behavior of TwelveLabs API v1.3 so developers can understand it precisely.

### 10.1 Indexing Phase

```
[What the developer does]
1. client.indexes.create() → Create index (register Marengo + Pegasus)
2. client.tasks.create() → Upload video & start indexing (async)
3. Poll task.status or wait for webhook → Analysis available when "ready"

[What happens internally at TwelveLabs]
- Marengo: Splits video into 2~10 second segments (shot boundary detection)
  → Embeds each segment as a 1024-dimensional vector
  → These vectors become the search targets for search.query()
- Pegasus: Internally encodes the video's visual+audio representations
  → Reasoning is based on this encoding when analyze() is called
```

**Segment splitting rules:**
- Video: Split into semantic units via shot boundary detection (scene change detection)
- Each segment minimum 2 seconds, maximum 10 seconds
- Segments under 2 seconds at the end are automatically truncated
- Beauty tutorials have frequent cuts, so segments tend to be short → advantageous for precise violation detection

### 10.2 Phase 1: Embed-Based Cosine Similarity

```
[API Calls]
# 1. Retrieve pre-indexed segment embeddings
video = client.indexes.videos.retrieve(
    index_id, video_id,
    embedding_option=["visual", "audio"]
)
segments = video.embedding.video_embedding.segments

# 2. Create text embedding for the campaign query
text_emb = client.embed.v_2.create(
    model_name="marengo3.0",
    input_type="text",
    text=query_text
)

# 3. Compute cosine similarity locally
for segment in segments:
    score = cosine_similarity(segment.float_, text_emb.float_)

[Internal Behavior]
1. Retrieves the video segment embedding vectors generated during indexing
2. Creates a text embedding vector for the campaign relevance query
3. Computes cosine similarity between text embedding and each segment vector locally

[Interpreting Results]
- Many matching segments with high scores → video highly related to campaign
- Few matching segments or low scores → video unrelated to campaign
- This does NOT create new video embeddings — it retrieves existing embeddings
  → Very low additional cost

[Why not Search API]
- Search API returns relative rank scores (useful for sorting results, not for
  absolute relevance judgment). Direct embedding comparison yields absolute 0~1
  cosine similarity scores, which are more suitable for threshold-based filtering.
```

### 10.3 Phase 2: Pegasus Analyze

```
[API Call]
client.analyze(
    video_id, prompt + schema_hint
)

[Internal Behavior]
1. Pegasus "watches" the indexed video from start to finish
   (integrated understanding of visual + audio + on-screen text)
2. Performs reasoning according to prompt instructions
3. Generates structured results conforming to the prompt-embedded JSON Schema

[Key Difference - Embed Similarity vs Analyze]
- Embed Similarity: Mathematical similarity computation between embedding vectors (fast and cheap)
- Analyze: Watches the entire video and reasons in natural language (slow and expensive)
- Embed Similarity: "Is this video related to beauty?" (Yes/No + absolute score)
- Analyze: "What's happening at 01:23, and why is it a problem?" (reasoning)
```

### 10.4 Embedding Retrieval (For Cross-Modal Verification)

**Note**: Phase 1 (Section 10.2) now also uses this same embedding retrieval mechanism for campaign relevance scoring. The retrieval below serves a second purpose: cross-modal consistency verification.

```
[API Call - Retrieve embeddings of indexed video]
video = client.indexes.indexed_assets.retrieve(
    index_id, indexed_asset_id,
    embedding_option=["visual", "audio"]
)
segments = video.embedding.video_embedding.segments

[Each segment structure]
- float_: 1024-dimensional embedding vector
- embedding_option: "visual" or "audio"
- start_offset_sec / end_offset_sec: time range

[Cross-modal verification]
Compute cosine similarity between visual_emb and audio_emb for the same time segment
→ If consistency < 0.4, visual-audio mismatch → re-analyze that segment with Pegasus
```

---

## 11. Threshold Configuration Rationale

### 11.1 Phase 1 Thresholds (Campaign Relevance)

| Threshold | Value | Rationale |
|---|---|---|
| OFF_BRIEF | < 0.3 | Cosine similarity below 0.3 means "nearly unrelated." Beauty keywords vs. gaming streams fall in this range |
| BORDERLINE | 0.3 ~ 0.6 | Related but not confident. E.g., ASMR + makeup hybrid content |
| ON_BRIEF | ≥ 0.6 | Clearly beauty/makeup content |

**Note**: These values are initial estimates. During the first 2 weeks of operation, all OFF_BRIEF BLOCKs should be treated as REVIEW to verify the actual distribution and then adjust accordingly.

### 11.2 Phase 2 Thresholds (Policy Violation Severity)

Why BLOCK/REVIEW thresholds differ by category:

| Category | BLOCK | REVIEW | Rationale |
|---|---|---|---|
| Hate/Harassment | 0.65 | 0.40 | Highest brand risk, so lowest threshold |
| Profanity | 0.80 | 0.50 | Mild profanity is common in the beauty domain. Higher threshold to prevent false positives |
| Drugs/Illegal | 0.60 | 0.35 | High legal risk, so lowest threshold |
| Unsafe Product Use | 0.70 | 0.45 | Requires context-dependent judgment, so mid-range |
| Medical Claims | 0.75 | 0.45 | Even LOW severity triggers REVIEW (regulatory sensitivity) |

### 11.3 Confidence Routing Thresholds

| Threshold | Value | Rationale |
|---|---|---|
| Auto-process | ≥ 0.9 | Ad compliance carries higher risk from false negatives than false positives. Conservative setting |
| REVIEW | 0.6 ~ 0.9 | Most videos fall in this range. Quick judgment using AI results as reference |
| Escalation | < 0.6 | AI is uncertain. Assign to senior reviewer |

---

## 12. Known Limitations and Trade-offs

### 12.1 Vendor Dependency

Fully dependent on the TwelveLabs API. Mitigation strategies:
- DLQ + automatic transition to manual review queue (graceful degradation)
- When routed through Bedrock, leverage AWS infrastructure-level availability guarantees
- Long-term consideration: add Gemini/Nova as supplementary verification models

### 12.2 Initial Threshold Uncertainty

All thresholds (0.3, 0.6, 0.9, etc.) are theoretical estimates. They may not match actual data.

**Mitigation Strategy: 2-Week Calibration Period**
```
Week 1~2: Treat all decisions as REVIEW
  → Manual reviewers verify AI decision accuracy
  → Collect (AI decision, actual result) pairs
  → Train Platt Scaling for score → actual probability mapping
  → Adjust thresholds

Week 3~: Begin auto-processing with adjusted thresholds
  → Continuous monitoring + monthly recalibration
```

### 12.3 Beauty Domain False Positives

Most frequently expected false positive types:

| Expression | AI Judgment (False Positive) | Actual Meaning |
|---|---|---|
| "This color is killer" | HATE_HARASSMENT | Positive colloquial expression |
| "This is insane" | PROFANITY | Exclamation of admiration |
| "My skin came back from the dead" | HATE_HARASSMENT | Describing product effectiveness |
| Tapping face with brush | UNSAFE_PRODUCT_USE | Makeup application technique |

**Mitigation Strategies:**
- Negative prompting: Include a "the following expressions are NOT violations" list in the prompt
- False positive DB: Accumulate confirmed false positive cases from manual reviews
- Monthly prompt updates: Add negative examples based on the false positive DB

### 12.4 Potential Quality Degradation from Consolidated Calls

Consolidating 5 policies into a single analyze call may degrade judgment quality for some categories due to longer prompts.

**Monitoring Approach:**
- Track false positive/negative rates separately per category
- If a specific category's false positive rate exceeds 10%, switch that category to a separate call
- Testing to date shows no significant quality degradation with 5-category consolidation

---

## 13. Implementation Notes

### 13.1 API Version

- **Must use v1.3 SDK**: `models` (not `engines`), `model_options` (not `engine_options`)
- `/generate` endpoint has been changed to `/analyze` (June 2025)
- `/gist`, `/summarize` sunset in February 2026 → replaced with `/analyze` + structured response

### 13.2 Index Management

- Models/modalities cannot be changed after index creation → enable Marengo + Pegasus + visual + audio from the start
- Index names must be unique → use environment-specific prefixes (e.g., `dev-compliance`, `prod-compliance`)
- Deleting an index also deletes all video data → use caution

### 13.3 Asynchronous Processing

- `tasks.create()` is asynchronous. Poll status using the returned task_id or set up a webhook
- Calling `search.query()` or `analyze()` before indexing completes will result in an error
- Webhook setup requires idempotency guarantees (duplicate event delivery is possible)

### 13.4 Error Handling

```python
# Required error handling pattern
try:
    result = client.analyze(video_id=vid, prompt=prompt)
    data = json.loads(result.data)
except twelvelabs.APIError as e:
    if e.status_code == 429:
        # Rate limit → exponential backoff retry
        retry_with_backoff()
    elif e.status_code == 404:
        # Video not indexed → check indexing status
        check_indexing_status()
    else:
        # Other errors → move to DLQ
        send_to_dlq(video_id, error=str(e))
except json.JSONDecodeError:
    # Possible without response_format enforcement → retry
    retry_once()
```

### 13.5 Testing Strategy

| Test Type | Target | Method |
|---|---|---|
| Unit tests | Decision Engine threshold logic | Verify decisions with mock API responses |
| Integration tests | Full pipeline | Test index + 5~10 sample videos |
| Golden set tests | Accuracy regression prevention | Periodic verification with 50 manually labeled videos |
| Threshold validation | Post-calibration | A/B test (original thresholds vs. adjusted thresholds) |

---

*This document should be read alongside architecture.md. architecture.md describes "what," and this document describes "why."*
