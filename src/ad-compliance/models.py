"""Domain models for the compliance pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class BriefLabel(str, Enum):
    ON_BRIEF = "ON_BRIEF"
    BORDERLINE = "BORDERLINE"
    OFF_BRIEF = "OFF_BRIEF"


@dataclass
class Violation:
    category: str
    severity: Severity
    timestamp_start: str
    reason: str
    timestamp_end: Optional[str] = None
    confidence: float = 0.0


@dataclass
class Phase1Result:
    score: float
    label: BriefLabel


@dataclass
class Phase2Result:
    overall_status: str
    summary: str
    violations: list[Violation] = field(default_factory=list)


@dataclass
class EvidenceReport:
    video_id: str
    index_id: str
    submitted_at: str
    analyzed_at: str
    processing_time_seconds: float
    decision: Decision
    decision_reasoning: str
    video_description: str
    campaign_relevance: dict
    policy_violations: list[dict]
    violation_summary: dict
