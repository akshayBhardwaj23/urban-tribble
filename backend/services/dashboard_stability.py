"""Keep dashboard layout stable across data refreshes unless schema changes."""

from __future__ import annotations

import json
from typing import Any, Optional


def column_signature(metadata: dict[str, Any]) -> frozenset[str]:
    """Normalized column names used to detect schema drift."""
    cols = metadata.get("all_columns")
    if not cols:
        parts: list[str] = []
        for key in (
            "date_columns",
            "revenue_columns",
            "category_columns",
            "numeric_columns",
            "text_columns",
        ):
            parts.extend(metadata.get(key) or [])
        cols = parts
    return frozenset(str(c).strip().lower() for c in cols if c)


def schema_changed(old_metadata: Optional[dict], new_metadata: dict) -> bool:
    if not old_metadata:
        return True
    return column_signature(old_metadata) != column_signature(new_metadata)


def should_rebuild_dashboard_plan(
    *,
    dashboard_plan_locked: bool,
    old_metadata: Optional[dict],
    new_metadata: dict,
    existing_plan_json: Optional[str],
) -> bool:
    """Return True when dashboard planner should run (new layout)."""
    if not existing_plan_json:
        return True
    if not dashboard_plan_locked:
        return True
    return schema_changed(old_metadata, new_metadata)


def parse_metadata_json(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
