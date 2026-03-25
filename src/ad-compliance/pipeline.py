"""Full pipeline orchestrator – runs Step 0 through Step 5."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .client import get_client
from .decision import decide, route
from .evidence import build_report, report_to_json
from .indexing import get_or_create_index
from .ingestion import ingest_video
from .models import BriefLabel, Decision
from .phase1_search import run_phase1
from .phase2_analyze import run_phase2

log = logging.getLogger(__name__)


def run_pipeline(
    *,
    url: str | None = None,
    file_path: str | None = None,
    index_name: str | None = None,
) -> dict:
    """Execute the full compliance pipeline for a single video.

    Returns the evidence report as a dict.
    """
    submitted_at = datetime.now(timezone.utc)
    client = get_client()

    # Step 0 – Index
    log.info("=== Step 0: Index ===")
    kwargs = {"client": client}
    if index_name:
        kwargs["index_name"] = index_name
    index_id = get_or_create_index(**kwargs)

    # Step 1 – Ingest
    log.info("=== Step 1: Ingest ===")
    video_id = ingest_video(index_id, url=url, file_path=file_path, client=client)

    # Step 2 – Phase 1: Campaign relevance
    log.info("=== Step 2: Phase 1 (Search) ===")
    phase1 = run_phase1(index_id, video_id, client=client)

    # Phase 1 early exit: off-brief → BLOCK, skip Phase 2
    phase2 = None
    if phase1.label != BriefLabel.OFF_BRIEF:
        # Step 3 – Phase 2: Policy analysis
        log.info("=== Step 3: Phase 2 (Analyze) ===")
        phase2 = run_phase2(video_id, client=client)

    # Step 4 – Decision
    log.info("=== Step 4: Decision ===")
    decision, reasoning, confidence = decide(phase1, phase2)
    handling = route(decision, confidence)
    log.info("Decision=%s confidence=%.2f route=%s", decision.value, confidence, handling)

    # Step 5 – Evidence Report
    log.info("=== Step 5: Evidence Report ===")
    report = build_report(
        video_id, index_id, submitted_at,
        phase1, phase2, decision, reasoning,
        client=client,
    )

    return {
        "report": report,
        "report_json": report_to_json(report),
        "route": handling,
    }
