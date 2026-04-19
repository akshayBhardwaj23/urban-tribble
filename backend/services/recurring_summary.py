"""Build and persist workspace-level weekly / monthly executive summaries."""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

import pandas as pd
from openai import OpenAI
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models.models import WorkspaceRecurringSummary
from services.cleaned_parquet import CleanedDataMissingError, ensure_cleaned_parquet
from services.period_change_summary import build_workspace_what_changed
from services.workspace_query import dataset_upload_pairs_for_workspace

_KINDS = frozenset({"weekly", "monthly"})


def _load_cleaned_df(upload: Any) -> pd.DataFrame:
    try:
        p = ensure_cleaned_parquet(upload)
    except CleanedDataMissingError as e:
        raise FileNotFoundError(str(e)) from e
    return pd.read_parquet(str(p))


def _last_completed_iso_week(today: date) -> tuple[date, date]:
    """Monday–Sunday of the most recent fully completed week before ``today``."""
    if today.weekday() == 6:
        end = today - timedelta(days=7)
    else:
        end = today - timedelta(days=today.weekday() + 1)
    start = end - timedelta(days=6)
    return start, end


def _previous_calendar_month(today: date) -> tuple[date, date]:
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, last_prev


def _period_bounds(kind: str, today: date) -> tuple[date, date, str]:
    if kind == "weekly":
        start, end = _last_completed_iso_week(today)
        label = _week_label(start, end)
        return start, end, label
    if kind == "monthly":
        start, end = _previous_calendar_month(today)
        label = start.strftime("%B %Y")
        return start, end, label
    raise ValueError(f"Unknown summary kind: {kind}")


def _week_label(start: date, end: date) -> str:
    if start.month == end.month and start.year == end.year:
        inner = f"{start.strftime('%b %d')}–{end.strftime('%d, %Y')}"
    elif start.year == end.year:
        inner = f"{start.strftime('%b %d')}–{end.strftime('%b %d, %Y')}"
    else:
        inner = f"{start.strftime('%b %d, %Y')}–{end.strftime('%b %d, %Y')}"
    return f"Week of {inner}"


def _heuristic_content(
    wc: dict[str, Any],
    period_label: str,
) -> dict[str, Any]:
    if not wc.get("available"):
        return {
            "headline": f"{period_label}: not enough overlapping dates to compare periods yet.",
            "key_changes": [
                "Import or append rows so each source spans the summary window and the prior window.",
            ],
            "biggest_risk": "Decisions without a clean period baseline invite false confidence.",
            "biggest_opportunity": "Lock primary date and amount columns so automated reads stay trustworthy.",
            "recommended_actions": [
                "Verify date columns are transaction-level, not file-import timestamps.",
                "Backfill the latest week or month if systems lag.",
            ],
        }

    highlights = list(wc.get("highlights") or [])
    items = list(wc.get("items") or [])
    key_changes: list[str] = []
    cross = wc.get("cross_metric_note")
    if cross:
        key_changes.append(str(cross).strip())
    for h in highlights[:3]:
        expl = (h.get("explanation") or "").strip()
        if expl and expl not in key_changes:
            key_changes.append(expl)
    for it in items[:4]:
        expl = (it.get("explanation") or "").strip()
        if expl and expl not in key_changes and len(key_changes) < 4:
            key_changes.append(expl)
    key_changes = key_changes[:4]
    if not key_changes:
        key_changes = ["Moves are small versus the last window—watch next period for confirmation."]

    def _mag(it: dict[str, Any]) -> float:
        p = it.get("delta_pct")
        if p is not None:
            return abs(float(p))
        return abs(float(it.get("current_value", 0)) - float(it.get("previous_value", 0)))

    unfav = [i for i in items if i.get("is_favorable") is False]
    fav = [i for i in items if i.get("is_favorable") is True]

    if unfav:
        worst = max(unfav, key=_mag)
        risk_line = str(worst.get("explanation") or "").strip() or (
            f"{worst.get('label')} weakened versus the prior window—trace drivers before you scale."
        )
    elif cross and re.search(r"spend|cost|expense", str(cross), re.I):
        risk_line = str(cross).strip()
    else:
        risk_line = (
            "No single metric screams downside in this scan—still pressure-test assumptions with finance."
        )

    if fav:
        best = max(fav, key=_mag)
        opp_line = str(best.get("explanation") or "").strip() or (
            f"{best.get('label')} improved versus the prior window—validate repeatability."
        )
    else:
        opp_line = "Hunt for mix, timing, or segment stories the headline KPIs may be hiding."

    actions: list[str] = []
    if cross:
        actions.append("Align revenue and spend narratives with whoever owns weekly P&L variance.")
    for h in highlights:
        lab = str(h.get("label", "")).lower()
        if "expense" in lab or "spend" in lab:
            actions.append("Triage top spend buckets before approving incremental budget.")
            break
    for h in highlights:
        lab = str(h.get("label", "")).lower()
        if "revenue" in lab or "profit" in lab:
            actions.append("Pressure-test pipeline and attribution so growth is not a one-week blip.")
            break
    if len(actions) < 2:
        actions.append("Pick one hypothesis from this summary and assign an owner with a Friday readout.")
    actions = actions[:3]

    h0 = highlights[0] if highlights else None
    if h0:
        head = (
            f"{period_label}: {h0.get('label', 'Key metric')} {h0.get('arrow', '')} "
            f"versus the prior window."
        )
    else:
        head = f"{period_label}: period-over-period comparison is ready."

    return {
        "headline": head[:240],
        "key_changes": key_changes,
        "biggest_risk": risk_line[:500],
        "biggest_opportunity": opp_line[:500],
        "recommended_actions": actions,
    }


_LLM_SYSTEM = """You refine a short executive summary for a business operator.
Return JSON only with keys: headline, key_changes (array 3-4 strings), biggest_risk, biggest_opportunity, recommended_actions (array 2-3 strings).
Rules: decisive, practical, no filler, no emoji, each bullet skimmable in seconds. Keep headline under 140 characters."""


def _maybe_polish_with_llm(
    draft: dict[str, Any],
    what_changed: dict[str, Any],
) -> dict[str, Any]:
    if not settings.OPENAI_API_KEY:
        return draft
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    payload = {
        "draft": draft,
        "period_note": what_changed.get("period_description"),
        "highlights": what_changed.get("highlights"),
        "cross_metric_note": what_changed.get("cross_metric_note"),
    }
    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(payload, default=str)[:12000],
                },
            ],
            temperature=0.35,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content or "{}"
        out = json.loads(raw)
        merged = {
            "headline": str(out.get("headline") or draft["headline"])[:240],
            "key_changes": out.get("key_changes") or draft["key_changes"],
            "biggest_risk": str(out.get("biggest_risk") or draft["biggest_risk"])[:500],
            "biggest_opportunity": str(
                out.get("biggest_opportunity") or draft["biggest_opportunity"]
            )[:500],
            "recommended_actions": out.get("recommended_actions")
            or draft["recommended_actions"],
        }
        if not isinstance(merged["key_changes"], list):
            merged["key_changes"] = draft["key_changes"]
        if not isinstance(merged["recommended_actions"], list):
            merged["recommended_actions"] = draft["recommended_actions"]
        merged["key_changes"] = [str(x) for x in merged["key_changes"]][:4]
        merged["recommended_actions"] = [str(x) for x in merged["recommended_actions"]][
            :3
        ]
        return merged
    except Exception:
        return draft


def render_email_html_snapshot(
    period_label: str,
    kind: str,
    content: dict[str, Any],
) -> str:
    """Static HTML fragment for future transactional email (no send)."""
    h = html.escape
    lines = [
        f"<p><strong>{h(period_label)}</strong> · {h(kind)} digest</p>",
        f"<p>{h(str(content.get('headline', '')))}</p>",
        "<p><strong>Key changes</strong></p><ul>",
    ]
    for c in content.get("key_changes") or []:
        lines.append(f"<li>{h(str(c))}</li>")
    lines.append("</ul>")
    lines.append(f"<p><strong>Risk</strong><br>{h(str(content.get('biggest_risk', '')))}</p>")
    lines.append(
        f"<p><strong>Opportunity</strong><br>{h(str(content.get('biggest_opportunity', '')))}</p>"
    )
    lines.append("<p><strong>Recommended actions</strong></p><ul>")
    for a in content.get("recommended_actions") or []:
        lines.append(f"<li>{h(str(a))}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def _existing_row(
    db: Session,
    workspace_id: str,
    kind: str,
    period_start: date,
) -> Optional[WorkspaceRecurringSummary]:
    return (
        db.query(WorkspaceRecurringSummary)
        .filter(
            WorkspaceRecurringSummary.workspace_id == workspace_id,
            WorkspaceRecurringSummary.kind == kind,
            WorkspaceRecurringSummary.period_start == period_start,
        )
        .first()
    )


def ensure_summary_for_period(
    db: Session,
    workspace_id: str,
    kind: str,
    *,
    today: Optional[date] = None,
    force_refresh: bool = False,
) -> Optional[WorkspaceRecurringSummary]:
    """Create or return stored summary for the canonical period (last week / prior month)."""
    if kind not in _KINDS:
        raise ValueError("kind must be weekly or monthly")
    today = today or date.today()
    start_d, end_d, label = _period_bounds(kind, today)
    start_ts = pd.Timestamp(start_d)
    end_ts = pd.Timestamp(end_d)

    existing = _existing_row(db, workspace_id, kind, start_d)
    if existing and not force_refresh:
        return existing

    pairs = dataset_upload_pairs_for_workspace(db, workspace_id).all()
    if not pairs:
        return None

    wc = build_workspace_what_changed(
        pairs,
        _load_cleaned_df,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    content = _heuristic_content(wc, label)
    content = _maybe_polish_with_llm(content, wc)
    enriched = {
        **content,
        "meta": {
            "period_kind": kind,
            "period_label": label,
            "what_changed_available": bool(wc.get("available")),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    }
    html_snap = render_email_html_snapshot(label, kind, content)

    if existing and force_refresh:
        existing.period_end = end_d
        existing.period_label = label
        existing.content_json = json.dumps(enriched)
        existing.email_html_snapshot = html_snap
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    row = WorkspaceRecurringSummary(
        workspace_id=workspace_id,
        kind=kind,
        period_start=start_d,
        period_end=end_d,
        period_label=label,
        content_json=json.dumps(enriched),
        email_html_snapshot=html_snap,
        email_sent_at=None,
        email_scheduled=None,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        return _existing_row(db, workspace_id, kind, start_d)


def latest_stored_summary(
    db: Session,
    workspace_id: str,
    kind: str,
) -> Optional[WorkspaceRecurringSummary]:
    return (
        db.query(WorkspaceRecurringSummary)
        .filter(
            WorkspaceRecurringSummary.workspace_id == workspace_id,
            WorkspaceRecurringSummary.kind == kind,
        )
        .order_by(WorkspaceRecurringSummary.period_start.desc())
        .first()
    )


def list_summary_history(
    db: Session,
    workspace_id: str,
    kind: str,
    limit: int,
) -> list[WorkspaceRecurringSummary]:
    return (
        db.query(WorkspaceRecurringSummary)
        .filter(
            WorkspaceRecurringSummary.workspace_id == workspace_id,
            WorkspaceRecurringSummary.kind == kind,
        )
        .order_by(WorkspaceRecurringSummary.period_start.desc())
        .limit(limit)
        .all()
    )


def serialize_summary_row(row: WorkspaceRecurringSummary) -> dict[str, Any]:
    content = json.loads(row.content_json) if row.content_json else {}
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "kind": row.kind,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "period_label": row.period_label,
        "content": content,
        "email_ready": bool(row.email_html_snapshot),
        "email_sent_at": row.email_sent_at.isoformat() if row.email_sent_at else None,
        "email_scheduled": row.email_scheduled,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
