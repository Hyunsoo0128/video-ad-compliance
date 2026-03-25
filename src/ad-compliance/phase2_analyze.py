"""Step 3 – Phase 2: Pegasus Analyze for policy violation detection (§6).

Single analyze() call checks all 5 policy categories simultaneously.
Uses JSON Schema response_format for guaranteed structured output.
"""

from __future__ import annotations

import json
import logging

from twelvelabs.types import ResponseFormat

from .client import get_client, retry_call
from .config import POLICY_CODES
from .models import Phase2Result, Severity, Violation
from .prompts import COMPLIANCE_PROMPT

log = logging.getLogger(__name__)

# JSON Schema enforced on Pegasus output – §6.3 / §6.6
ANALYSIS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "overall_status": {
            "type": "string",
            "enum": ["APPROVE", "REVIEW", "BLOCK"],
        },
        "summary": {"type": "string"},
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": POLICY_CODES},
                    "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "timestamp_start": {"type": "string"},
                    "timestamp_end": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["category", "severity", "timestamp_start", "reason"],
            },
        },
    },
    "required": ["overall_status", "summary", "violations"],
}


def run_phase2(video_id: str, *, client=None) -> Phase2Result:
    """Analyze video for policy violations. Returns structured result."""
    client = client or get_client()

    result = retry_call(
        client.analyze,
        video_id=video_id,
        prompt=COMPLIANCE_PROMPT,
        response_format=ResponseFormat(
            type="json_schema",
            json_schema=ANALYSIS_SCHEMA,
        ),
    )

    data = json.loads(result.data)

    violations = [
        Violation(
            category=v["category"],
            severity=Severity(v["severity"]),
            timestamp_start=v["timestamp_start"],
            timestamp_end=v.get("timestamp_end"),
            reason=v["reason"],
        )
        for v in data.get("violations", [])
    ]

    log.info("Phase 2: status=%s violations=%d", data["overall_status"], len(violations))
    return Phase2Result(
        overall_status=data["overall_status"],
        summary=data["summary"],
        violations=violations,
    )
