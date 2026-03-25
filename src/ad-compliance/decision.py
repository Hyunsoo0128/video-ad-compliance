"""Step 4 – Decision Engine (§7).

Combines Phase 1 + Phase 2 results into a final APPROVE / REVIEW / BLOCK
decision using the priority matrix from §7.2.
"""

from __future__ import annotations

import logging

from .config import AUTO_CONFIDENCE, REVIEW_CONFIDENCE
from .models import BriefLabel, Decision, Phase1Result, Phase2Result, Severity

log = logging.getLogger(__name__)


def decide(phase1: Phase1Result, phase2: Phase2Result | None) -> tuple[Decision, str, float]:
    """Return (decision, reasoning, confidence).

    Priority order (§7.2):
      1. OFF_BRIEF → BLOCK
      2. HIGH severity → BLOCK
      3. MEDIUM severity → REVIEW
      4. BORDERLINE relevance → REVIEW
      5. MEDICAL_CLAIMS any severity → REVIEW
      6. Otherwise → APPROVE
    """
    # 1. Off-brief → BLOCK (Phase 2 was skipped)
    if phase1.label == BriefLabel.OFF_BRIEF:
        return Decision.BLOCK, "Off-brief: content unrelated to campaign", 0.95

    if phase2 is None:
        return Decision.REVIEW, "Phase 2 result unavailable", 0.5

    violations = phase2.violations

    # 2. HIGH severity → BLOCK
    highs = [v for v in violations if v.severity == Severity.HIGH]
    if highs:
        conf = min(0.95, 0.7 + 0.05 * len(highs))
        return Decision.BLOCK, f"HIGH severity violation detected: {len(highs)} case(s)", conf

    # 3. MEDIUM severity → REVIEW
    mediums = [v for v in violations if v.severity == Severity.MEDIUM]
    if mediums:
        conf = 0.6 + 0.05 * len(mediums)
        return Decision.REVIEW, f"MEDIUM severity violation detected: {len(mediums)} case(s)", conf

    # 4. Borderline relevance → REVIEW
    if phase1.label == BriefLabel.BORDERLINE:
        return Decision.REVIEW, "Campaign relevance BORDERLINE", 0.65

    # 5. Medical claims (any severity) → REVIEW
    medical = [v for v in violations if v.category == "MEDICAL_CLAIMS"]
    if medical:
        return Decision.REVIEW, "Medical claims detected (regulatory sensitive)", 0.7

    # 6. All clear
    return Decision.APPROVE, "No violations found", 0.95


def route(decision: Decision, confidence: float) -> str:
    """Determine handling route based on confidence (§7.4)."""
    if confidence >= AUTO_CONFIDENCE:
        return "AUTO"
    elif confidence >= REVIEW_CONFIDENCE:
        return "REVIEW_QUEUE"
    else:
        return "ESCALATION"
