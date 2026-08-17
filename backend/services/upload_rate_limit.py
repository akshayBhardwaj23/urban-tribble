"""Fixed-window rate limiting backed by the database.

An in-process dict only limits one worker, so N workers multiplied the real
limit by N and every deploy reset it. Counters live in a table instead, keyed by
subject and window slot, so all workers share one budget.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models.models import RateLimitCounter

logger = logging.getLogger(__name__)

_PRUNE_EVERY = 200
_calls_since_prune = 0


def _slot(now: datetime, seconds: int) -> int:
    return int(now.timestamp()) // seconds


def _hit(db: Session, bucket_key: str, window_seconds: int, now: datetime) -> int:
    """Increment a window counter and return the new count."""
    expires_at = now + timedelta(seconds=window_seconds * 2)

    # UPDATE first: the common path is an existing window, and this is atomic.
    result = db.execute(
        update(RateLimitCounter)
        .where(RateLimitCounter.bucket_key == bucket_key)
        .values(hits=RateLimitCounter.hits + 1, expires_at=expires_at)
    )
    if result.rowcount:
        db.commit()
        row = (
            db.query(RateLimitCounter)
            .filter(RateLimitCounter.bucket_key == bucket_key)
            .first()
        )
        return int(row.hits) if row else 1

    try:
        db.add(
            RateLimitCounter(
                id=str(uuid4()), bucket_key=bucket_key, hits=1, expires_at=expires_at
            )
        )
        db.commit()
        return 1
    except IntegrityError:
        # Another worker created the same window between our UPDATE and INSERT.
        db.rollback()
        db.execute(
            update(RateLimitCounter)
            .where(RateLimitCounter.bucket_key == bucket_key)
            .values(hits=RateLimitCounter.hits + 1, expires_at=expires_at)
        )
        db.commit()
        row = (
            db.query(RateLimitCounter)
            .filter(RateLimitCounter.bucket_key == bucket_key)
            .first()
        )
        return int(row.hits) if row else 1


def _maybe_prune(db: Session, now: datetime) -> None:
    global _calls_since_prune
    _calls_since_prune += 1
    if _calls_since_prune < _PRUNE_EVERY:
        return
    _calls_since_prune = 0
    try:
        db.execute(delete(RateLimitCounter).where(RateLimitCounter.expires_at < now))
        db.commit()
    except Exception as exc:  # noqa: BLE001 — pruning must never fail a request
        db.rollback()
        logger.info("rate limit prune skipped: %s", exc)


def check_rate_limit(
    db: Session,
    subject: str,
    *,
    scope: str,
    per_minute: int,
    per_hour: int,
) -> None:
    """Raise 429 when ``subject`` exceeds either window for ``scope``."""
    if not subject:
        return

    key = subject.strip().lower()
    now = datetime.utcnow()

    minute_key = f"{scope}:{key}:m:{_slot(now, 60)}"
    if per_minute > 0 and _hit(db, minute_key, 60, now) > per_minute:
        raise HTTPException(
            429,
            detail=f"Too many {scope} requests. Wait a minute and try again.",
            headers={"Retry-After": "60"},
        )

    hour_key = f"{scope}:{key}:h:{_slot(now, 3600)}"
    if per_hour > 0 and _hit(db, hour_key, 3600, now) > per_hour:
        raise HTTPException(
            429,
            detail=f"Hourly {scope} limit reached. Try again later.",
            headers={"Retry-After": "600"},
        )

    _maybe_prune(db, now)


def check_upload_rate_limit(db: Session, user_email: str | None) -> None:
    check_rate_limit(
        db,
        user_email or "",
        scope="upload",
        per_minute=settings.UPLOAD_RATE_BURST_PER_MINUTE,
        per_hour=settings.UPLOAD_RATE_MAX_PER_HOUR,
    )


def hit_custom_window(
    db: Session,
    subject: str,
    *,
    scope: str,
    window_seconds: int,
) -> int:
    """Increment a custom-length window and return the new hit count."""
    if not subject:
        return 0
    key = subject.strip().lower()
    now = datetime.utcnow()
    bucket = f"{scope}:{key}:w:{_slot(now, window_seconds)}"
    count = _hit(db, bucket, window_seconds, now)
    _maybe_prune(db, now)
    return count


def peek_custom_window(
    db: Session,
    subject: str,
    *,
    scope: str,
    window_seconds: int,
) -> int:
    """Return current hits for a custom window without incrementing."""
    if not subject:
        return 0
    key = subject.strip().lower()
    now = datetime.utcnow()
    bucket = f"{scope}:{key}:w:{_slot(now, window_seconds)}"
    row = (
        db.query(RateLimitCounter)
        .filter(RateLimitCounter.bucket_key == bucket)
        .first()
    )
    return int(row.hits) if row else 0


def reset_upload_rate_limit_for_tests(db: Session | None = None) -> None:
    global _calls_since_prune
    _calls_since_prune = 0
    if db is not None:
        db.execute(delete(RateLimitCounter))
        db.commit()
