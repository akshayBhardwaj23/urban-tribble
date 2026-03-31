"""In-memory upload rate limits per user email.

Sufficient for a single process. For multiple workers or horizontal scale, replace
with Redis or enforce limits at the reverse proxy (e.g. nginx limit_req).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import DefaultDict, List

from fastapi import HTTPException

from config import settings

_lock = threading.Lock()
_timestamps: DefaultDict[str, List[float]] = defaultdict(list)


def check_upload_rate_limit(user_email: str) -> None:
    if not user_email:
        return

    now = time.time()
    burst = settings.UPLOAD_RATE_BURST_PER_MINUTE
    hourly = settings.UPLOAD_RATE_MAX_PER_HOUR
    window_hour = 3600.0
    window_min = 60.0

    key = user_email.strip().lower()

    with _lock:
        ts = _timestamps[key]
        ts[:] = [t for t in ts if now - t < window_hour]

        in_last_minute = sum(1 for t in ts if now - t < window_min)
        if in_last_minute >= burst:
            raise HTTPException(
                status_code=429,
                detail="Too many uploads in a short period. Please wait a minute and try again.",
            )
        if len(ts) >= hourly:
            raise HTTPException(
                status_code=429,
                detail="Hourly upload limit reached. Try again later.",
            )
        ts.append(now)


def reset_upload_rate_limit_for_tests() -> None:
    """Clear all counters (tests only)."""
    with _lock:
        _timestamps.clear()
