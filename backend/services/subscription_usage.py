"""Plan caps + monthly usage for subscription-aware UI (limits enforced later via billing)."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from models.models import Analysis, Dataset, Upload, UploadStatus, User, WorkspaceTimelineSnapshot

_PLAN_LABELS = {
    "free": "Free",
    "starter": "Starter",
    "pro": "Pro",
}

# None = unlimited for that meter. Aligns with marketing on /pricing.
_CAPS: dict[str, dict[str, Optional[int]]] = {
    "free": {
        "analyses_per_month": 2,
        "uploads_per_month": 2,
        "history_periods": 0,
    },
    "starter": {
        "analyses_per_month": 15,
        "uploads_per_month": 10,
        "history_periods": 3,
    },
    "pro": {
        "analyses_per_month": None,
        "uploads_per_month": 30,
        "history_periods": 24,
    },
}


def _month_start_utc(now: Optional[datetime] = None) -> datetime:
    n = now or datetime.utcnow()
    return datetime(n.year, n.month, 1)


def _effective_plan_id() -> str:
    raw = (getattr(settings, "SUBSCRIPTION_PLAN", None) or "free").lower().strip()
    return raw if raw in _CAPS else "free"


def _count_workspace_briefings_this_month(
    db: Session, workspace_id: str, month_start: datetime
) -> int:
    n = db.query(func.count(Analysis.id))
    n = n.join(Dataset, Analysis.dataset_id == Dataset.id)
    n = n.join(Upload, Dataset.upload_id == Upload.id)
    return int(
        n.filter(
            Upload.workspace_id == workspace_id,
            Analysis.type == "workspace_overview",
            Analysis.created_at >= month_start,
        ).scalar()
        or 0
    )


def _count_workspace_uploads_this_month(
    db: Session, workspace_id: str, month_start: datetime
) -> int:
    return int(
        db.query(func.count(Upload.id))
        .filter(
            Upload.workspace_id == workspace_id,
            Upload.status == UploadStatus.completed,
            Upload.created_at >= month_start,
        )
        .scalar()
        or 0
    )


def _count_timeline_snapshots(db: Session, workspace_id: str) -> int:
    return int(
        db.query(func.count(WorkspaceTimelineSnapshot.id))
        .filter(WorkspaceTimelineSnapshot.workspace_id == workspace_id)
        .scalar()
        or 0
    )


def _meter(used: int, limit: Optional[int]) -> Optional[dict[str, Any]]:
    if limit is None:
        return None
    pct = min(1.0, used / limit) if limit > 0 else 0.0
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "pct": round(pct * 100, 1),
        "approaching": pct >= 0.75,
        "at_limit": used >= limit,
    }


def build_workspace_usage_payload(
    db: Session,
    user: User,
    workspace_id: str,
) -> dict[str, Any]:
    _ = user.id  # future: per-account plan from billing
    plan = _effective_plan_id()
    caps = _CAPS[plan]
    month_start = _month_start_utc()
    last_day = monthrange(month_start.year, month_start.month)[1]
    month_end = datetime(month_start.year, month_start.month, last_day) + timedelta(days=1)

    analyses_used = _count_workspace_briefings_this_month(db, workspace_id, month_start)
    uploads_used = _count_workspace_uploads_this_month(db, workspace_id, month_start)
    snapshots = _count_timeline_snapshots(db, workspace_id)

    hp = caps.get("history_periods")
    hist_cap = 0 if hp == 0 else (hp if hp is not None else 3)
    periods_highlight = min(snapshots, hist_cap) if snapshots and hist_cap > 0 else 0

    meter_a = _meter(analyses_used, caps.get("analyses_per_month"))
    meter_u = _meter(uploads_used, caps.get("uploads_per_month"))

    nudges: list[dict[str, str]] = []
    if meter_a and meter_a["approaching"]:
        nudges.append({
            "tone": "approaching" if meter_a["at_limit"] else "soft",
            "message": (
                f"You've used {analyses_used}/{meter_a['limit']} workspace analyses "
                f"this month—higher plans include more monthly runs."
            ),
            "href": "/pricing",
        })
    if meter_u and meter_u["approaching"] and len(nudges) < 2:
        nudges.append({
            "tone": "approaching" if meter_u["at_limit"] else "soft",
            "message": (
                f"You've used {uploads_used}/{meter_u['limit']} uploads "
                f"this month on {_PLAN_LABELS.get(plan, plan)}."
            ),
            "href": "/pricing",
        })
    if plan == "free" and hist_cap == 0 and len(nudges) < 2:
        nudges.append({
            "tone": "soft",
            "message": (
                "History and alerts are on paid plans—see Starter and Pro on the pricing page."
            ),
            "href": "/pricing",
        })
    elif plan == "free" and snapshots > hist_cap and hist_cap > 0 and len(nudges) < 2:
        nudges.append({
            "tone": "soft",
            "message": (
                "Upgrade to track more historical data—Pro keeps a longer comparison window."
            ),
            "href": "/pricing",
        })
    if plan == "free" and len(nudges) == 0:
        nudges.append({
            "tone": "whisper",
            "message": (
                "Pro unlocks higher monthly limits and deeper history for alerts and briefings."
            ),
            "href": "/pricing",
        })

    if hist_cap == 0:
        history_summary = f"No period comparison on {_PLAN_LABELS.get(plan, plan)}"
    else:
        history_summary = (
            f"Tracking up to {hist_cap} comparison periods on {_PLAN_LABELS.get(plan, plan)}"
            + (f" · {snapshots} checkpoints saved" if snapshots else "")
        )

    return {
        "plan_id": plan,
        "plan_label": _PLAN_LABELS.get(plan, plan.title()),
        "period_start": month_start.date().isoformat(),
        "period_end": month_end.date().isoformat(),
        "limits": {
            "analyses_per_month": caps.get("analyses_per_month"),
            "uploads_per_month": caps.get("uploads_per_month"),
            "history_periods": hist_cap,
        },
        "usage": {
            "analyses_this_month": analyses_used,
            "uploads_this_month": uploads_used,
            "timeline_snapshots": snapshots,
        },
        "history": {
            "periods_cap": hist_cap,
            "snapshots_recorded": snapshots,
            "periods_highlighted": periods_highlight,
            "summary": history_summary,
        },
        "meters": {
            "analyses": meter_a,
            "uploads": meter_u,
        },
        "nudges": nudges[:2],
    }
