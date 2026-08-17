"""Short-lived cache for the workspace overview.

Building the overview reads and aggregates every dataset's parquet. The
dashboard polls it on every navigation, so an unchanged workspace was paying
that cost repeatedly. The cache key includes a fingerprint of the workspace's
datasets, so any upload, append, delete or re-map invalidates it immediately.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.models import Dataset, Upload

TTL_SECONDS = 60
_MAX_ENTRIES = 256

_entries: dict[str, tuple[str, float, Any]] = {}
_lock = threading.Lock()


def fingerprint(db: Session, workspace_id: str) -> str:
    """Cheap signature of everything the overview depends on."""
    row = (
        db.query(
            func.count(Dataset.id),
            func.max(Dataset.created_at),
            func.max(Upload.created_at),
            func.sum(func.coalesce(Upload.row_count, 0)),
        )
        .select_from(Dataset)
        .join(Upload, Dataset.upload_id == Upload.id)
        .filter(Upload.workspace_id == workspace_id)
        .one()
    )
    return "|".join("" if v is None else str(v) for v in row)


def get_or_build(
    db: Session,
    workspace_id: str,
    build: Callable[[], Any],
    *,
    extra_key: str = "",
) -> Any:
    key = f"{workspace_id}:{extra_key}"
    signature = fingerprint(db, workspace_id)
    now = time.time()

    with _lock:
        hit = _entries.get(key)
        if hit and hit[0] == signature and now - hit[1] < TTL_SECONDS:
            return hit[2]

    value = build()

    with _lock:
        if len(_entries) >= _MAX_ENTRIES:
            for stale, _ in sorted(
                ((k, v[1]) for k, v in _entries.items()), key=lambda kv: kv[1]
            )[: _MAX_ENTRIES // 4]:
                _entries.pop(stale, None)
        _entries[key] = (signature, now, value)

    return value


def invalidate(workspace_id: str | None = None) -> None:
    with _lock:
        if workspace_id is None:
            _entries.clear()
            return
        for key in [k for k in _entries if k.startswith(f"{workspace_id}:")]:
            _entries.pop(key, None)
