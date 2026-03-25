"""Step 5 – Evidence Report generation (§8).

Produces a structured JSON report with decision, violations, and video summary.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from .client import get_client, retry_call
from .models import Decision, EvidenceReport, Phase1Result, Phase2Result, Violation

log = logging.getLogger(__name__)


def _summarize_video(video_id: str, client=None) -> str:
    """Generate a 2-5 sentence factual summary via Pegasus (§8.2)."""
    client = client or get_client()
    try:
        result = retry_call(
            client.analyze,
            video_id=video_id,
            prompt=(
                "Summarize this video in 2-5 sentences. "
                "Include: products shown, demonstration content, mood, and setting."
            ),
        )
        return result.data
    except Exception as exc:
        log.warning("Video summary failed: %s", exc)
        return ""


def build_report(
    video_id: str,
    index_id: str,
    submitted_at: datetime,
    phase1: Phase1Result,
    phase2: Phase2Result | None,
    decision: Decision,
    reasoning: str,
    *,
    client=None,
) -> EvidenceReport:
    """Assemble the evidence report."""
    now = datetime.now(timezone.utc)

    description = _summarize_video(video_id, client=client)

    violations_dicts = []
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    if phase2:
        for v in phase2.violations:
            violations_dicts.append({
                "category": v.category,
                "severity": v.severity.value,
                "timestamp_start": v.timestamp_start,
                "timestamp_end": v.timestamp_end,
                "reason": v.reason,
                "confidence": v.confidence,
            })
            severity_counts[v.severity.value.lower()] += 1

    return EvidenceReport(
        video_id=video_id,
        index_id=index_id,
        submitted_at=submitted_at.isoformat(),
        analyzed_at=now.isoformat(),
        processing_time_seconds=(now - submitted_at).total_seconds(),
        decision=decision,
        decision_reasoning=reasoning,
        video_description=description,
        campaign_relevance={
            "score": phase1.score,
            "label": phase1.label.value,
        },
        policy_violations=violations_dicts,
        violation_summary={
            "total": len(violations_dicts),
            **severity_counts,
        },
    )


def report_to_json(report: EvidenceReport) -> str:
    d = asdict(report)
    d["decision"] = report.decision.value
    return json.dumps(d, indent=2, ensure_ascii=False)
