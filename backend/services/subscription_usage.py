"""Per-user plan caps, usage meters, and enforcement helpers."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from utils.email_norm import normalize_email
from models.models import (
    Analysis,
    ChatMessage,
    Dataset,
    Upload,
    UploadStatus,
    User,
    Workspace,
    WorkspaceTimelineSnapshot,
)
from services.plan_limits import raise_plan_limit

PLAN_IDS = frozenset({"free", "starter", "pro", "internal"})
_ANALYSIS_TYPES_FOR_CAP = ("overview", "workspace_overview")

_PLAN_LABELS = {
    "free": "Free",
    "starter": "Starter",
    "pro": "Pro",
    "internal": "Internal",
}

# Lifetime totals (free tier) — uploads & AI analyses across all owned workspaces.
_FREE_LIFETIME = {"uploads": 2, "analyses": 2}

# Per-calendar-month caps for starter/pro (per workspace for uploads & analyses).
_MONTHLY_CAPS = {
    "starter": {"uploads": 10, "analyses": 15},
    "pro": {"uploads": 30, "analyses": None},
    # Same generous caps as Pro but higher upload ceiling for fixture-heavy testing.
    "internal": {"uploads": 500, "analyses": None},
}

_HISTORY_PERIODS = {"free": 0, "starter": 3, "pro": 24, "internal": 24}

_WORKSPACES_MAX = {"free": 1, "starter": 1, "pro": 5, "internal": 50}

# Max user-authored chat messages: lifetime (free) or per UTC calendar month (starter/pro).
_CHAT_USER_CAPS = {"free": 3, "starter": 50, "pro": 200, "internal": 1_000_000}


def _internal_test_login_user(user: User) -> bool:
    """Allowlisted mailbox with test sign-in enabled — treated as internal (no practical limits)."""
    if not getattr(settings, "AUTH_TEST_LOGIN_ENABLED", False):
        return False
    allowed = (getattr(settings, "AUTH_TEST_LOGIN_EMAIL", None) or "").strip()
    if not allowed:
        return False
    return normalize_email(user.email) == normalize_email(allowed)


def get_effective_plan(_db: Session, user: User) -> str:
    if _internal_test_login_user(user):
        return "internal"
    force = (getattr(settings, "FORCE_SUBSCRIPTION_PLAN", None) or "").strip().lower()
    if force in PLAN_IDS:
        return force
    raw = (getattr(user, "subscription_plan", None) or "free").strip().lower()
    return raw if raw in PLAN_IDS else "free"


def plan_features(plan: str) -> dict[str, Any]:
    p = plan if plan in PLAN_IDS else "free"
    pro_like = p in ("pro", "internal")
    return {
        "timeline": p != "free",
        "what_changed": p != "free",
        "alerts": pro_like,
        "weekly_summary": pro_like,
        "monthly_summary": p != "free",
        "full_briefing": p != "free",
    }


def workspaces_max_for(plan: str) -> int:
    return _WORKSPACES_MAX.get(plan if plan in PLAN_IDS else "free", 1)


def history_periods_cap(plan: str) -> int:
    return int(_HISTORY_PERIODS.get(plan if plan in PLAN_IDS else "free", 0))


def empty_what_changed() -> dict[str, Any]:
    return {
        "available": False,
        "period_description": "",
        "items": [],
        "highlights": [],
        "cross_metric_note": None,
    }


def trim_free_analysis_result(result: dict[str, Any]) -> dict[str, Any]:
    """Shorter Free-tier briefing without re-calling the model."""
    out = dict(result)
    for key, n in (
        ("top_priorities", 2),
        ("key_metrics", 4),
        ("insights", 2),
        ("anomalies", 2),
        ("recommendations", 2),
    ):
        v = out.get(key)
        if isinstance(v, list) and len(v) > n:
            out[key] = v[:n]
    return out


def _month_start_utc(now: Optional[datetime] = None) -> datetime:
    n = now or datetime.utcnow()
    return datetime(n.year, n.month, 1)


def _count_workspace_analyses_this_month(
    db: Session, workspace_id: str, month_start: datetime
) -> int:
    q = db.query(func.count(Analysis.id))
    q = q.join(Dataset, Analysis.dataset_id == Dataset.id)
    q = q.join(Upload, Dataset.upload_id == Upload.id)
    return int(
        q.filter(
            Upload.workspace_id == workspace_id,
            Analysis.type.in_(_ANALYSIS_TYPES_FOR_CAP),
            Analysis.created_at >= month_start,
        ).scalar()
        or 0
    )


def _count_user_analyses_all_time(db: Session, user_id: str) -> int:
    q = db.query(func.count(Analysis.id))
    q = q.join(Dataset, Analysis.dataset_id == Dataset.id)
    q = q.join(Upload, Dataset.upload_id == Upload.id)
    q = q.join(Workspace, Upload.workspace_id == Workspace.id)
    return int(
        q.filter(
            Workspace.owner_id == user_id,
            Analysis.type.in_(_ANALYSIS_TYPES_FOR_CAP),
        ).scalar()
        or 0
    )


def _count_user_completed_uploads_all_time(db: Session, user_id: str) -> int:
    return int(
        db.query(func.count(Upload.id))
        .join(Workspace, Upload.workspace_id == Workspace.id)
        .filter(
            Workspace.owner_id == user_id,
            Upload.status == UploadStatus.completed,
        )
        .scalar()
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


def _count_user_chat_user_messages(
    db: Session,
    user_id: str,
    month_start: Optional[datetime] = None,
) -> int:
    q = (
        db.query(func.count(ChatMessage.id))
        .join(Dataset, ChatMessage.dataset_id == Dataset.id)
        .join(Upload, Dataset.upload_id == Upload.id)
        .join(Workspace, Upload.workspace_id == Workspace.id)
        .filter(Workspace.owner_id == user_id, ChatMessage.role == "user")
    )
    if month_start is not None:
        q = q.filter(ChatMessage.created_at >= month_start)
    return int(q.scalar() or 0)


def _count_timeline_snapshots(db: Session, workspace_id: str) -> int:
    return int(
        db.query(func.count(WorkspaceTimelineSnapshot.id))
        .filter(WorkspaceTimelineSnapshot.workspace_id == workspace_id)
        .scalar()
        or 0
    )


def _owned_workspace_count(db: Session, user_id: str) -> int:
    return int(
        db.query(func.count(Workspace.id))
        .filter(Workspace.owner_id == user_id)
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
    plan = get_effective_plan(db, user)
    month_start = _month_start_utc()
    last_day = monthrange(month_start.year, month_start.month)[1]
    month_end = datetime(month_start.year, month_start.month, last_day) + timedelta(days=1)
    hist_cap = history_periods_cap(plan)
    snapshots = _count_timeline_snapshots(db, workspace_id)

    if plan == "free":
        analyses_used = _count_user_analyses_all_time(db, user.id)
        uploads_used = _count_user_completed_uploads_all_time(db, user.id)
        analyses_limit = _FREE_LIFETIME["analyses"]
        uploads_limit = _FREE_LIFETIME["uploads"]
        meter_period_label = "lifetime (Free)"
        analyses_label = "analyses (lifetime)"
        uploads_label = "uploads (lifetime)"
    else:
        analyses_used = _count_workspace_analyses_this_month(db, workspace_id, month_start)
        uploads_used = _count_workspace_uploads_this_month(db, workspace_id, month_start)
        caps = _MONTHLY_CAPS.get(plan, _MONTHLY_CAPS["starter"])
        analyses_limit = caps["analyses"]
        uploads_limit = caps["uploads"]
        meter_period_label = "this month"
        analyses_label = "analyses this month"
        uploads_label = "uploads this month"

    periods_highlight = min(snapshots, hist_cap) if snapshots and hist_cap > 0 else 0
    meter_a = _meter(analyses_used, analyses_limit)
    meter_u = _meter(uploads_used, uploads_limit)

    chat_cap = _CHAT_USER_CAPS.get(plan, 3)
    chat_used = (
        _count_user_chat_user_messages(db, user.id, None)
        if plan == "free"
        else _count_user_chat_user_messages(db, user.id, month_start)
    )
    meter_chat = _meter(chat_used, chat_cap)

    nudges: list[dict[str, str]] = []
    if meter_a and meter_a["approaching"]:
        nudges.append({
            "tone": "approaching" if meter_a["at_limit"] else "soft",
            "message": (
                f"You've used {analyses_used}/{meter_a['limit']} {analyses_label}—"
                f"higher plans include more runs."
            ),
            "href": "/pricing",
        })
    if meter_u and meter_u["approaching"] and len(nudges) < 2:
        nudges.append({
            "tone": "approaching" if meter_u["at_limit"] else "soft",
            "message": (
                f"You've used {uploads_used}/{meter_u['limit']} {uploads_label} "
                f"on {_PLAN_LABELS.get(plan, plan)}."
            ),
            "href": "/pricing",
        })
    if meter_chat and meter_chat["approaching"] and len(nudges) < 2:
        nudges.append({
            "tone": "approaching" if meter_chat["at_limit"] else "soft",
            "message": (
                f"Chat: {chat_used}/{meter_chat['limit']} messages ({meter_period_label.strip('()')})."
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
    elif plan == "starter" and len(nudges) < 2:
        nudges.append({
            "tone": "whisper",
            "message": "Pro adds weekly summaries, alerts, and more workspaces.",
            "href": "/pricing",
        })
    if plan == "free" and len(nudges) == 0:
        nudges.append({
            "tone": "whisper",
            "message": (
                "Upgrade for monthly data limits, history, and full AI briefings."
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
        "meter_period_label": meter_period_label,
        "period_start": month_start.date().isoformat(),
        "period_end": month_end.date().isoformat(),
        "limits": {
            "analyses_cap": analyses_limit,
            "uploads_cap": uploads_limit,
            "history_periods": hist_cap,
            "chat_messages_cap": chat_cap,
        },
        "usage": {
            "analyses_count": analyses_used,
            "uploads_count": uploads_used,
            "timeline_snapshots": snapshots,
            "chat_user_messages": chat_used,
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
            "chat": meter_chat,
        },
        "nudges": nudges[:2],
    }


def assert_upload_allowed(db: Session, user: User, workspace_id: str) -> None:
    plan = get_effective_plan(db, user)
    if plan == "free":
        used = _count_user_completed_uploads_all_time(db, user.id)
        lim = _FREE_LIFETIME["uploads"]
        if used >= lim:
            raise_plan_limit(
                plan,
                "uploads",
                f"Free plan allows {lim} data uploads total. Upgrade for more.",
            )
        return
    caps = _MONTHLY_CAPS.get(plan)
    if not caps:
        return
    lim = caps["uploads"]
    month_start = _month_start_utc()
    used = _count_workspace_uploads_this_month(db, workspace_id, month_start)
    if used >= lim:
        raise_plan_limit(
            plan,
            "uploads",
            f"You've reached {lim} uploads this month on your plan.",
        )


def assert_analysis_allowed(db: Session, user: User, workspace_id: str) -> None:
    plan = get_effective_plan(db, user)
    if plan == "free":
        used = _count_user_analyses_all_time(db, user.id)
        lim = _FREE_LIFETIME["analyses"]
        if used >= lim:
            raise_plan_limit(
                plan,
                "analyses",
                f"Free plan allows {lim} analysis runs total. Upgrade for more.",
            )
        return
    caps = _MONTHLY_CAPS.get(plan)
    if not caps:
        return
    lim = caps["analyses"]
    if lim is None:
        return
    month_start = _month_start_utc()
    used = _count_workspace_analyses_this_month(db, workspace_id, month_start)
    if used >= lim:
        raise_plan_limit(
            plan,
            "analyses",
            f"You've reached {lim} analysis runs this month for this workspace.",
        )


def assert_workspace_create_allowed(db: Session, user: User) -> None:
    plan = get_effective_plan(db, user)
    mx = workspaces_max_for(plan)
    n = _owned_workspace_count(db, user.id)
    if n >= mx:
        raise_plan_limit(
            plan,
            "workspaces",
            f"Your plan allows up to {mx} workspace(s). Upgrade to add more.",
        )


def assert_timeline_allowed(db: Session, user: User) -> None:
    plan = get_effective_plan(db, user)
    if not plan_features(plan)["timeline"]:
        raise_plan_limit(
            plan,
            "timeline",
            "Timeline and history views require Starter or Pro.",
        )


def assert_summary_allowed(db: Session, user: User, kind: str) -> None:
    plan = get_effective_plan(db, user)
    feats = plan_features(plan)
    if kind == "weekly" and not feats["weekly_summary"]:
        raise_plan_limit(
            plan,
            "weekly_summary",
            "Weekly summaries are available on Pro.",
        )
    if kind == "monthly" and not feats["monthly_summary"]:
        raise_plan_limit(
            plan,
            "monthly_summary",
            "Monthly summaries require a paid plan.",
        )


def assert_chat_allowed(db: Session, user: User) -> None:
    plan = get_effective_plan(db, user)
    cap = _CHAT_USER_CAPS.get(plan, 3)
    if plan == "free":
        used = _count_user_chat_user_messages(db, user.id, None)
    else:
        used = _count_user_chat_user_messages(db, user.id, _month_start_utc())
    if used >= cap:
        scope = "lifetime" if plan == "free" else "this month"
        raise_plan_limit(
            plan,
            "chat",
            f"Chat limit reached ({cap} messages {scope} on your plan).",
        )
