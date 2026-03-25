# Ad Compliance Pipeline

AI-powered video ad compliance and brand safety automation for a global makeup brand campaign.

Uses **TwelveLabs Marengo 3.0** (search) + **Pegasus 1.2** (analysis/generation) to automatically analyze creator videos and produce APPROVE / REVIEW / BLOCK decisions with timestamped evidence.

## Architecture

```
Video → Indexing → Phase 1 (Search) → Phase 2 (Analyze) → Decision → Evidence Report
         Marengo     Marengo Search      Pegasus Analyze     Engine     JSON Report
        +Pegasus     campaign fit?       5 policy checks     matrix     + summary
```

See [`docs/architecture-structure.md`](docs/architecture-structure.md) for the full design document.

## Quick Start

```bash
# 1. Setup
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env with your TWELVELABS_API_KEY

# 3. Run with a URL
ad-compliance --url "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" -v

# 4. Run with a local file
ad-compliance --file video.mp4 -v

# 5. Save report to file
ad-compliance --file video.mp4 -o report.json
```

## Example Output

### Non-beauty video → BLOCK (OFF_BRIEF)

```
$ ad-compliance --url "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" -v

2026-03-25 11:30:08 INFO     ad_compliance.pipeline: === Step 0: Index ===
2026-03-25 11:30:08 INFO     ad_compliance.indexing: Using existing index ad-compliance-prod
2026-03-25 11:30:08 INFO     ad_compliance.pipeline: === Step 1: Ingest ===
2026-03-25 11:30:09 INFO     ad_compliance.ingestion: Video already indexed (filename=ForBiggerBlazes.mp4)
2026-03-25 11:30:09 INFO     ad_compliance.pipeline: === Step 2: Phase 1 (Search) ===
2026-03-25 11:30:22 INFO     ad_compliance.phase1_search: Phase 1: matched_clips=0 score=0.000 label=OFF_BRIEF
2026-03-25 11:30:22 INFO     ad_compliance.pipeline: === Step 4: Decision ===
2026-03-25 11:30:22 INFO     ad_compliance.pipeline: Decision=BLOCK confidence=0.95 route=AUTO
2026-03-25 11:30:22 INFO     ad_compliance.pipeline: === Step 5: Evidence Report ===
{
  "decision": "BLOCK",
  "decision_reasoning": "Off-brief: content unrelated to campaign",
  "campaign_relevance": { "score": 0.0, "label": "OFF_BRIEF" },
  "policy_violations": [],
  "violation_summary": { "total": 0, "high": 0, "medium": 0, "low": 0 }
}
```

No clips matched the campaign query → OFF_BRIEF → immediate BLOCK. Phase 2 (policy analysis) is skipped entirely.

### Beauty video → APPROVE

```
$ ad-compliance --file test_beauty.mp4 -v

2026-03-25 11:30:57 INFO     ad_compliance.pipeline: === Step 0: Index ===
2026-03-25 11:30:58 INFO     ad_compliance.indexing: Using existing index ad-compliance-prod
2026-03-25 11:30:58 INFO     ad_compliance.pipeline: === Step 1: Ingest ===
2026-03-25 11:30:58 INFO     ad_compliance.ingestion: Video already indexed (filename=test_beauty.mp4)
2026-03-25 11:30:58 INFO     ad_compliance.pipeline: === Step 2: Phase 1 (Search) ===
2026-03-25 11:31:01 INFO     ad_compliance.phase1_search: Phase 1: matched_clips=6 score=1.000 label=ON_BRIEF
2026-03-25 11:31:01 INFO     ad_compliance.pipeline: === Step 3: Phase 2 (Analyze) ===
2026-03-25 11:31:06 INFO     ad_compliance.phase2_analyze: Phase 2: status=APPROVE violations=0
2026-03-25 11:31:06 INFO     ad_compliance.pipeline: === Step 4: Decision ===
2026-03-25 11:31:06 INFO     ad_compliance.pipeline: Decision=APPROVE confidence=0.95 route=AUTO
2026-03-25 11:31:06 INFO     ad_compliance.pipeline: === Step 5: Evidence Report ===
{
  "decision": "APPROVE",
  "decision_reasoning": "No violations found",
  "campaign_relevance": { "score": 1.0, "label": "ON_BRIEF" },
  "policy_violations": [],
  "violation_summary": { "total": 0, "high": 0, "medium": 0, "low": 0 }
}
```

6 clips matched → ON_BRIEF → Phase 2 policy analysis → no violations → APPROVE.

### Beauty video with policy violations → BLOCK (PROFANITY + MEDICAL_CLAIMS)

```
$ ad-compliance --file test_beauty_violations.mp4 -v

2026-03-25 14:04:28 INFO     ad_compliance.pipeline: === Step 0: Index ===
2026-03-25 14:04:28 INFO     ad_compliance.indexing: Using existing index ad-compliance-prod
2026-03-25 14:04:28 INFO     ad_compliance.pipeline: === Step 1: Ingest ===
2026-03-25 14:04:28 INFO     ad_compliance.ingestion: Video already indexed (filename=test_beauty_violations.mp4)
2026-03-25 14:04:28 INFO     ad_compliance.pipeline: === Step 2: Phase 1 (Search) ===
2026-03-25 14:04:28 INFO     ad_compliance.phase1_search: Phase 1: matched_clips=3 score=1.000 label=ON_BRIEF
2026-03-25 14:04:28 INFO     ad_compliance.pipeline: === Step 3: Phase 2 (Analyze) ===
2026-03-25 14:04:36 INFO     ad_compliance.phase2_analyze: Phase 2: status=BLOCK violations=3
2026-03-25 14:04:36 INFO     ad_compliance.pipeline: === Step 4: Decision ===
2026-03-25 14:04:36 INFO     ad_compliance.pipeline: Decision=BLOCK confidence=0.80 route=REVIEW_QUEUE
2026-03-25 14:04:36 INFO     ad_compliance.pipeline: === Step 5: Evidence Report ===
{
  "decision": "BLOCK",
  "decision_reasoning": "HIGH severity violation detected: 2 case(s)",
  "campaign_relevance": { "score": 1.0, "label": "ON_BRIEF" },
  "policy_violations": [
    {
      "category": "MEDICAL_CLAIMS",
      "severity": "HIGH",
      "timestamp_start": "0s",
      "timestamp_end": "10s",
      "reason": "Spoken claim: 'cures my acne and heals all my skin problems'"
    },
    {
      "category": "MEDICAL_CLAIMS",
      "severity": "HIGH",
      "timestamp_start": "10s",
      "timestamp_end": "15s",
      "reason": "Spoken claim: 'treats eczema and removes wrinkles permanently'"
    },
    {
      "category": "PROFANITY",
      "severity": "MEDIUM",
      "timestamp_start": "0s",
      "timestamp_end": "10s",
      "reason": "Spoken expression: 'this fucking foundation is incredible'"
    }
  ],
  "violation_summary": { "total": 3, "high": 2, "medium": 1, "low": 0 }
}
```

3 clips matched → ON_BRIEF → Phase 2 detects spoken profanity and medical claims → BLOCK (HIGH severity violations).

## Pipeline Steps

| Step | Module | Model | Description |
|------|--------|-------|-------------|
| 0 | `indexing.py` | — | Create dual-model index (Marengo + Pegasus) |
| 1 | `ingestion.py` | Both | Upload & index video (skips duplicates by filename) |
| 2 | `phase1_search.py` | Marengo | Campaign relevance via search clip matching |
| 3 | `phase2_analyze.py` | Pegasus | 5-category policy violation analysis |
| 4 | `decision.py` | — | Priority-based decision matrix |
| 5 | `evidence.py` | Pegasus | Evidence report with video summary |

## Phase 1: Campaign Relevance (Search-Based)

Uses `search.query` to find clips matching the campaign query.

- Matched clips found → ON_BRIEF → proceed to Phase 2
- No matched clips → OFF_BRIEF → immediate BLOCK (Phase 2 skipped)
- Retries up to 5 times (3s interval) to handle search index propagation delay after fresh ingestion
- Duplicate videos detected by filename — reuses existing video_id, no re-indexing

## Phase 2: Policy Violation Analysis

Single Pegasus `analyze()` call checks all 5 categories simultaneously. The JSON Schema is embedded in the prompt text (not via `response_format`) to ensure full audio+visual analysis:

1. **HATE_HARASSMENT** – Hateful speech, bullying, discrimination
2. **PROFANITY** – Explicit language, vulgar expressions
3. **DRUGS_ILLEGAL** – Drug references, illegal activity
4. **UNSAFE_PRODUCT_USE** – Cosmetics used dangerously
5. **MEDICAL_CLAIMS** – Unsubstantiated health claims

## Decision Matrix

| Priority | Condition | Verdict |
|----------|-----------|---------|
| 1 | OFF_BRIEF | BLOCK |
| 2 | HIGH severity violation | BLOCK |
| 3 | MEDIUM severity violation | REVIEW |
| 4 | BORDERLINE relevance | REVIEW |
| 5 | Any MEDICAL_CLAIMS | REVIEW |
| 6 | All clear | APPROVE |

## Exit Codes

| Code | Decision |
|------|----------|
| 0 | APPROVE |
| 1 | REVIEW |
| 2 | BLOCK |

## Project Structure

```
src/ad_compliance/
├── cli.py              # CLI entry point
├── pipeline.py         # Orchestrator (Step 0→5)
├── config.py           # Thresholds, policy definitions
├── models.py           # Domain models
├── client.py           # TwelveLabs client + retry
├── indexing.py          # Step 0: Index creation
├── ingestion.py         # Step 1: Video upload (with dedup)
├── phase1_search.py     # Step 2: Marengo search (clip matching + retry)
├── phase2_analyze.py    # Step 3: Pegasus analyze
├── decision.py          # Step 4: Decision engine
├── evidence.py          # Step 5: Evidence report
└── prompts.py           # Compliance prompt

docs/
└── architecture-structure.md  # Full engineering design document
```

## SDK Compatibility Notes

- `ApiError`: imported from `twelvelabs.core` (not `twelvelabs.APIError`)
- `IndexesCreateRequestModelsItem`: imported from `twelvelabs.indexes.types` (not `twelvelabs.models`)
- `search.query`: returns `SearchItem` with `rank`, `start`, `end`, `video_id` — `score`/`confidence` fields are None in the current SDK version
