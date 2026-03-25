"""TwelveLabs client wrapper with retry / rate-limit handling (§11.2–11.3)."""

from __future__ import annotations

import logging
import random
import time

from twelvelabs import TwelveLabs
from twelvelabs.core import ApiError

from .config import TWELVELABS_API_KEY, RETRY

log = logging.getLogger(__name__)


def get_client() -> TwelveLabs:
    return TwelveLabs(api_key=TWELVELABS_API_KEY)


def retry_call(fn, *args, **kwargs):
    """Execute *fn* with exponential backoff on 429 / transient errors."""
    for attempt in range(1, RETRY.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except ApiError as exc:
            if exc.status_code == 429 and attempt < RETRY.max_retries:
                delay = min(RETRY.base_delay * (2 ** (attempt - 1)), RETRY.max_delay)
                delay += random.uniform(0, delay * 0.25)  # jitter
                log.warning("Rate-limited (429). Retry %d/%d in %.1fs",
                            attempt, RETRY.max_retries, delay)
                time.sleep(delay)
            elif exc.status_code >= 500 and attempt < RETRY.max_retries:
                delay = RETRY.base_delay * attempt
                log.warning("Server error %d. Retry %d/%d in %.1fs",
                            exc.status_code, attempt, RETRY.max_retries, delay)
                time.sleep(delay)
            else:
                raise
