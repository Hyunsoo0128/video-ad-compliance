"""Step 2 – Phase 1: 캠페인 관련성 판단 (§5).

search.query로 캠페인 쿼리와 매칭되는 클립 수를 기반으로 관련성을 판단한다.
매칭 클립이 있으면 ON_BRIEF, 없으면 OFF_BRIEF.
인덱싱 직후 검색 반영 지연에 대비해 retry 로직을 포함한다.
"""

from __future__ import annotations

import logging
import time

from .client import get_client, retry_call
from .config import CAMPAIGN_QUERY
from .models import BriefLabel, Phase1Result

log = logging.getLogger(__name__)

SEARCH_RETRY_ATTEMPTS = 5
SEARCH_RETRY_DELAY = 3  # seconds


def run_phase1(
    index_id: str,
    video_id: str,
    *,
    query: str = CAMPAIGN_QUERY,
    client=None,
) -> Phase1Result:
    """search.query 클립 매칭 수 기반 관련성 판정."""
    client = client or get_client()

    matched = []
    for attempt in range(SEARCH_RETRY_ATTEMPTS):
        if attempt > 0:
            log.info("Phase 1: retry %d/%d – waiting for search index propagation",
                     attempt, SEARCH_RETRY_ATTEMPTS - 1)
            time.sleep(SEARCH_RETRY_DELAY)

        result = retry_call(
            client.search.query,
            index_id=index_id,
            query_text=query,
            search_options=["visual"],
            threshold="none",
        )
        matched = [c for c in result if c.video_id == video_id]
        if matched:
            break

    ratio = 1.0 if matched else 0.0
    label = BriefLabel.ON_BRIEF if matched else BriefLabel.OFF_BRIEF

    log.info("Phase 1: matched_clips=%d score=%.3f label=%s",
             len(matched), ratio, label.value)
    return Phase1Result(score=ratio, label=label)
