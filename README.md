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

# 3. Run — URL 방식
ad-compliance --url "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" -v

# 4. Run — 로컬 파일 방식
ad-compliance --file test_beauty.mp4 -v

# 5. JSON 파일로 저장
ad-compliance --file test_beauty.mp4 -o report.json
```

## Example Output

### 비뷰티 영상 → BLOCK (OFF_BRIEF)

```
$ ad-compliance --url "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" -v

2026-03-25 11:30:08 INFO     ad_compliance.pipeline: === Step 0: Index ===
2026-03-25 11:30:08 INFO     ad_compliance.indexing: Using existing index ad-compliance-prod (69c3430c6b6de9a96499b06c)
2026-03-25 11:30:08 INFO     ad_compliance.pipeline: === Step 1: Ingest ===
2026-03-25 11:30:09 INFO     ad_compliance.ingestion: Video already indexed (filename=ForBiggerBlazes.mp4) – video_id=69c345be6b6de9a96499b208
2026-03-25 11:30:09 INFO     ad_compliance.pipeline: === Step 2: Phase 1 (Search) ===
2026-03-25 11:30:22 INFO     ad_compliance.phase1_search: Phase 1: matched_clips=0 score=0.000 label=OFF_BRIEF
2026-03-25 11:30:22 INFO     ad_compliance.pipeline: === Step 4: Decision ===
2026-03-25 11:30:22 INFO     ad_compliance.pipeline: Decision=BLOCK confidence=0.95 route=AUTO
2026-03-25 11:30:22 INFO     ad_compliance.pipeline: === Step 5: Evidence Report ===
{
  "video_id": "69c345be6b6de9a96499b208",
  "decision": "BLOCK",
  "decision_reasoning": "Off-brief: content unrelated to campaign",
  "video_description": "The video opens with a dramatic scene from Game of Thrones on a tablet...",
  "campaign_relevance": {
    "score": 0.0,
    "label": "OFF_BRIEF"
  },
  "policy_violations": [],
  "violation_summary": { "total": 0, "high": 0, "medium": 0, "low": 0 }
}
```

Phase 1에서 캠페인 쿼리와 매칭되는 클립이 0개 → OFF_BRIEF → 즉시 BLOCK. Phase 2(정책 위반 분석)는 스킵됩니다.

### 뷰티 영상 → APPROVE

```
$ ad-compliance --file test_beauty.mp4 -v

2026-03-25 11:30:57 INFO     ad_compliance.pipeline: === Step 0: Index ===
2026-03-25 11:30:58 INFO     ad_compliance.indexing: Using existing index ad-compliance-prod (69c3430c6b6de9a96499b06c)
2026-03-25 11:30:58 INFO     ad_compliance.pipeline: === Step 1: Ingest ===
2026-03-25 11:30:58 INFO     ad_compliance.ingestion: Video already indexed (filename=test_beauty.mp4) – video_id=69c346765c31217163e8b979
2026-03-25 11:30:58 INFO     ad_compliance.pipeline: === Step 2: Phase 1 (Search) ===
2026-03-25 11:31:01 INFO     ad_compliance.phase1_search: Phase 1: matched_clips=6 score=1.000 label=ON_BRIEF
2026-03-25 11:31:01 INFO     ad_compliance.pipeline: === Step 3: Phase 2 (Analyze) ===
2026-03-25 11:31:06 INFO     ad_compliance.phase2_analyze: Phase 2: status=APPROVE violations=0
2026-03-25 11:31:06 INFO     ad_compliance.pipeline: === Step 4: Decision ===
2026-03-25 11:31:06 INFO     ad_compliance.pipeline: Decision=APPROVE confidence=0.95 route=AUTO
2026-03-25 11:31:06 INFO     ad_compliance.pipeline: === Step 5: Evidence Report ===
{
  "video_id": "69c346765c31217163e8b979",
  "decision": "APPROVE",
  "decision_reasoning": "No violations found",
  "video_description": "The video features a close-up demonstration of a makeup artist applying pink eyeshadow...",
  "campaign_relevance": {
    "score": 1.0,
    "label": "ON_BRIEF"
  },
  "policy_violations": [],
  "violation_summary": { "total": 0, "high": 0, "medium": 0, "low": 0 }
}
```

Phase 1에서 6개 클립 매칭 → ON_BRIEF → Phase 2 정책 위반 분석 → 위반 없음 → APPROVE.

## Pipeline Steps

| Step | Module | Model | Description |
|------|--------|-------|-------------|
| 0 | `indexing.py` | — | Create dual-model index (Marengo + Pegasus) |
| 1 | `ingestion.py` | Both | Upload & index video (filename 기반 중복 방지) |
| 2 | `phase1_search.py` | Marengo | Campaign relevance via search clip matching |
| 3 | `phase2_analyze.py` | Pegasus | 5-category policy violation analysis |
| 4 | `decision.py` | — | Priority-based decision matrix |
| 5 | `evidence.py` | Pegasus | Evidence report with video summary |

## Phase 1: Campaign Relevance (Search-Based)

`search.query`로 캠페인 쿼리와 매칭되는 클립을 검색합니다.

- 매칭 클립 존재 → ON_BRIEF → Phase 2 진행
- 매칭 클립 없음 → OFF_BRIEF → 즉시 BLOCK (Phase 2 스킵)
- 인덱싱 직후 검색 반영 지연 대응: 최대 5회 retry (3초 간격)
- 동일 filename 영상은 재인덱싱 없이 기존 video_id 재사용

## Phase 2: Policy Violation Analysis

단일 Pegasus `analyze()` 호출로 5개 카테고리를 동시 분석 (JSON Schema 강제):

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
├── client.py           # TwelveLabs client + retry (ApiError from twelvelabs.core)
├── indexing.py          # Step 0: Index creation
├── ingestion.py         # Step 1: Video upload (filename 기반 중복 방지)
├── phase1_search.py     # Step 2: Marengo search (clip matching + retry)
├── phase2_analyze.py    # Step 3: Pegasus analyze
├── decision.py          # Step 4: Decision engine
├── evidence.py          # Step 5: Evidence report
└── prompts.py           # Compliance prompt

docs/
└── architecture-structure.md  # Engineering design document
```

## SDK Compatibility Notes

- `ApiError`: `from twelvelabs.core import ApiError` (not `twelvelabs.APIError`)
- `IndexesCreateRequestModelsItem`: `from twelvelabs.indexes.types import ...` (not `twelvelabs.models`)
- `search.query`: returns `SearchItem` with `rank`, `start`, `end`, `video_id` — `score`/`confidence` are None in current SDK version
