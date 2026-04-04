"""Lightweight copy + timestamps to reinforce ongoing use of a workspace."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.models import Dataset, Upload, UploadStatus, WorkspaceTimelineSnapshot
from services.workspace_query import latest_workspace_overview_analysis


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.isoformat()
    return dt.isoformat() + "Z"


def _days_between(now: datetime, then: Optional[datetime]) -> Optional[int]:
    if then is None:
        return None
    try:
        return max(0, (now.date() - then.date()).days)
    except Exception:
        return None


def build_workspace_habit_hints(
    db: Session,
    workspace_id: str,
    *,
    has_datasets: bool,
) -> dict[str, Any]:
    now = datetime.utcnow()
    briefing = latest_workspace_overview_analysis(db, workspace_id)
    briefing_at = briefing.created_at if briefing else None

    latest_snap = (
        db.query(WorkspaceTimelineSnapshot)
        .filter(WorkspaceTimelineSnapshot.workspace_id == workspace_id)
        .order_by(WorkspaceTimelineSnapshot.created_at.desc())
        .first()
    )
    latest_snap_at = latest_snap.created_at if latest_snap else None

    max_upload_at = (
        db.query(func.max(Upload.created_at))
        .join(Dataset, Dataset.upload_id == Upload.id)
        .filter(
            Upload.workspace_id == workspace_id,
            Upload.status == UploadStatus.completed,
        )
        .scalar()
    )

    data_snap = (
        db.query(WorkspaceTimelineSnapshot)
        .filter(
            WorkspaceTimelineSnapshot.workspace_id == workspace_id,
            WorkspaceTimelineSnapshot.event_type.in_(("upload", "append")),
        )
        .order_by(WorkspaceTimelineSnapshot.created_at.desc())
        .first()
    )
    data_snap_at = data_snap.created_at if data_snap else None

    candidates_data = [t for t in (max_upload_at, data_snap_at) if t is not None]
    last_data_change_at = max(candidates_data) if candidates_data else None

    activity_pool = [
        t
        for t in (briefing_at, latest_snap_at, max_upload_at, data_snap_at)
        if t is not None
    ]
    last_activity_at = max(activity_pool) if activity_pool else None

    days_since_briefing = _days_between(now, briefing_at)
    days_since_data = _days_between(now, last_data_change_at)
    days_since_activity = _days_between(now, last_activity_at)

    next_check: str
    briefing_cta: str
    if not has_datasets:
        next_check = (
            "Once you import a file, run a briefing—then come back after each new drop "
            "of data or about weekly if volumes are steady."
        )
        briefing_cta = "After your first import."
        activity_nudge = None
        gentle_nudge = "Add a source to start an ongoing rhythm here."
    elif briefing_at is None:
        next_check = (
            "Run a workspace briefing to lock the baseline—then revisit after imports, "
            "appends, or about once a week."
        )
        briefing_cta = "Run the first briefing on this workspace."
        activity_nudge = (
            f"You last touched this workspace {days_since_activity} days ago."
            if days_since_activity is not None and days_since_activity >= 1
            else None
        )
        gentle_nudge = (
            "Import or append new rows when the business moves so comparisons stay honest."
        )
    elif last_data_change_at and briefing_at and last_data_change_at > briefing_at:
        next_check = (
            "New data landed after your last briefing—re-run when you want alerts, "
            "actions, and summaries aligned with the latest extracts."
        )
        briefing_cta = "After adding new data."
        activity_nudge = (
            "You have fresh data since the last briefing—worth a refresh."
        )
        gentle_nudge = None
    elif days_since_briefing is not None and days_since_briefing >= 7:
        next_check = (
            "It’s been a week or more since the last briefing—check again after new "
            "figures land, or run a quick refresh if you rely on this view for decisions."
        )
        briefing_cta = "Weekly or after new data."
        activity_nudge = _activity_line(days_since_activity)
        gentle_nudge = _gentle_data_line(days_since_data)
    else:
        next_check = (
            "Next recommended check: after your next import or row append—or next week "
            "if your files rarely change—to keep the story current."
        )
        briefing_cta = "After adding new data."
        activity_nudge = _activity_line(days_since_activity)
        gentle_nudge = _gentle_data_line(days_since_data)

    return {
        "last_activity_at": _iso_utc(last_activity_at),
        "last_briefing_at": _iso_utc(briefing_at),
        "last_data_change_at": _iso_utc(last_data_change_at),
        "days_since_activity": days_since_activity,
        "days_since_briefing": days_since_briefing,
        "days_since_data_change": days_since_data,
        "next_check_suggestion": next_check,
        "briefing_cta_context": briefing_cta,
        "activity_nudge": activity_nudge,
        "gentle_nudge": gentle_nudge,
    }


def _activity_line(days_since_activity: Optional[int]) -> Optional[str]:
    if days_since_activity is None or days_since_activity < 1:
        return None
    if days_since_activity == 1:
        return "You last updated this workspace yesterday."
    return f"You last updated this workspace {days_since_activity} days ago."


def _gentle_data_line(days_since_data: Optional[int]) -> Optional[str]:
    if days_since_data is None or days_since_data < 10:
        return None
    return (
        "If the business has moved since your last file change, upload or append "
        "so this workspace doesn’t trail reality."
    )
