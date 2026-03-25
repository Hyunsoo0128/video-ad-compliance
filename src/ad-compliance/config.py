"""Policy categories, thresholds, and pipeline configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# TwelveLabs
# ---------------------------------------------------------------------------
TWELVELABS_API_KEY: str = os.getenv("TWELVELABS_API_KEY", "")
INDEX_NAME: str = os.getenv("INDEX_NAME", "ad-compliance-prod")

# ---------------------------------------------------------------------------
# Policy categories – §6.2
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PolicyCategory:
    code: str
    label: str
    block_threshold: float
    review_threshold: float

POLICIES: list[PolicyCategory] = [
    PolicyCategory("HATE_HARASSMENT",    "Hate/Harassment",        0.65, 0.40),
    PolicyCategory("PROFANITY",          "Profanity",              0.80, 0.50),
    PolicyCategory("DRUGS_ILLEGAL",      "Drugs/Illegal Activity", 0.60, 0.35),
    PolicyCategory("UNSAFE_PRODUCT_USE", "Unsafe Product Use",     0.70, 0.45),
    PolicyCategory("MEDICAL_CLAIMS",     "Medical Claims",         0.75, 0.45),
]

# Per-category search queries for future multi-query Phase 1 expansion
SEARCH_QUERIES: dict[str, list[str]] = {
    "HATE_HARASSMENT": [
        "bullying or mocking someone",
        "discriminatory language or slurs",
        "harassing or intimidating behavior",
        "racist or sexist remarks",
        "body shaming or appearance mocking",
    ],
    "PROFANITY": [
        "profanity or swear words",
        "explicit or vulgar language",
        "offensive verbal expressions",
    ],
    "DRUGS_ILLEGAL": [
        "drug use or illegal substances",
        "smoking or vaping",
        "alcohol abuse or underage drinking",
        "illegal activity or criminal behavior",
    ],
    "UNSAFE_PRODUCT_USE": [
        "applying cosmetic product unsafely near eyes",
        "ingesting or eating makeup product",
        "using product on broken or irritated skin",
        "mixing cosmetic products dangerously",
        "applying product in a way that could cause harm",
    ],
    "MEDICAL_CLAIMS": [
        "claiming product cures skin condition",
        "medical or dermatological claims",
        "before and after with exaggerated results",
        "claiming product has healing or therapeutic effects",
        "misleading beauty or health claims",
    ],
}

POLICY_CODES: list[str] = [p.code for p in POLICIES]

# ---------------------------------------------------------------------------
# Phase 1 – §5.4
# search.query 클립 매칭 방식: 매칭 클립 존재 여부로 ON_BRIEF/OFF_BRIEF 판정
# (기존 코사인 유사도 임계값은 더 이상 사용하지 않음)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Decision confidence – §7.4
# ---------------------------------------------------------------------------
AUTO_CONFIDENCE: float = 0.9
REVIEW_CONFIDENCE: float = 0.6

# ---------------------------------------------------------------------------
# Campaign brief query – §5.2
# ---------------------------------------------------------------------------
CAMPAIGN_QUERY: str = os.getenv(
    "CAMPAIGN_QUERY",
    "beauty makeup tutorial product demonstration cosmetics review",
)

# ---------------------------------------------------------------------------
# Retry / rate-limit – §11.2
# ---------------------------------------------------------------------------
@dataclass
class RetryConfig:
    max_retries: int = 5
    base_delay: float = 2.0
    max_delay: float = 60.0

RETRY: RetryConfig = RetryConfig()
