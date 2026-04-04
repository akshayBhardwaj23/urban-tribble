"""Workspace timeline snapshots: metrics + themes over time for comparison and evolution."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from models.models import (
    Analysis,
    Dataset,
    Upload,
    UploadStatus,
    Workspace,
    WorkspaceRecurringSummary,
    WorkspaceTimelineSnapshot,
)
from services.workspace_query import dataset_upload_pairs_for_workspace

_THEME_BUCKETS: list[tuple[str, re.Pattern[str]]] = [
    ("marketing_efficiency", re.compile(
        r"marketing|campaign|spend|cpa|cpc|channel|ads|efficien", re.I
    )),
    ("margin_profit", re.compile(r"margin|profit|ebit|bottom|net\s*income", re.I)),
    ("revenue_growth", re.compile(r"revenue|sales|growth|gmv|booking|topline", re.I)),
    ("cost_pressure", re.compile(r"cost|expense|opex|overhead|burn", re.I)),
    ("data_quality", re.compile(r"duplicate|quality|missing|null|parse|invalid", re.I)),
    ("concentration", re.compile(r"concentrat|exposure|depend|skew", re.I)),
]

_PROFIT_KPI = re.compile(r"profit|margin|ebit|net", re.I)
_REV_KPI = re.compile(r"revenue|sales|gmv|booking", re.I)


def build_metrics_payload(db: Session, workspace_id: str) -> dict[str, Any]:
    """Current workspace KPI snapshot (ingest summaries)."""
    pairs = dataset_upload_pairs_for_workspace(db, workspace_id).all()
    total_rows = sum(up.row_count or 0 for _, up in pairs)
    kpis: list[dict[str, Any]] = []
    for ds, up in pairs:
        summary = json.loads(ds.data_summary) if ds.data_summary else {}
        metadata = json.loads(ds.schema_json) if ds.schema_json else {}
        for rev_col in metadata.get("revenue_columns", []):
            tk = f"{rev_col}_total"
            if tk in summary and isinstance(summary[tk], (int, float)):
                kpis.append({
                    "label": f"{rev_col.replace('_', ' ').title()}",
                    "value": float(summary[tk]),
                    "dataset_name": ds.name,
                })
    return {
        "workspace_row_total": int(total_rows),
        "dataset_count": len(pairs),
        "kpis": kpis[:16],
        "snapshot_quality": "live",
    }


def metrics_from_single_dataset(
    ds: Dataset,
    up: Upload,
    *,
    quality: str = "backfill",
) -> dict[str, Any]:
    summary = json.loads(ds.data_summary) if ds.data_summary else {}
    metadata = json.loads(ds.schema_json) if ds.schema_json else {}
    kpis: list[dict[str, Any]] = []
    for rev_col in metadata.get("revenue_columns", []):
        tk = f"{rev_col}_total"
        if tk in summary and isinstance(summary[tk], (int, float)):
            kpis.append({
                "label": f"{rev_col.replace('_', ' ').title()}",
                "value": float(summary[tk]),
                "dataset_name": ds.name,
            })
    return {
        "workspace_row_total": int(up.row_count or 0),
        "dataset_count": 1,
        "kpis": kpis[:16],
        "focus_dataset": ds.name,
        "snapshot_quality": quality,
    }


def themes_from_briefing_result(result: dict[str, Any]) -> dict[str, Any]:
    headlines: list[str] = []
    for ins in result.get("insights") or []:
        if isinstance(ins, dict):
            h = str(ins.get("headline", "")).strip()
            if h:
                headlines.append(h)
            p = str(ins.get("finding", "")).strip()
            if p and p not in headlines:
                headlines.append(p[:160])
    priorities: list[str] = []
    for pr in result.get("top_priorities") or []:
        if isinstance(pr, dict):
            t = str(pr.get("title", "")).strip()
            if t:
                priorities.append(t)
    exec_s = str(result.get("executive_summary", "")).strip()
    return {
        "insight_headlines": headlines[:12],
        "priority_titles": priorities[:8],
        "executive_snippet": exec_s[:280],
        "buckets": _collect_buckets(headlines + priorities + ([exec_s] if exec_s else [])),
    }


def _collect_buckets(texts: list[str]) -> list[str]:
    found: set[str] = set()
    for text in texts:
        for key, pat in _THEME_BUCKETS:
            if pat.search(text):
                found.add(key)
    return sorted(found)


def record_upload_snapshot(
    db: Session,
    workspace_id: str,
    upload: Upload,
    dataset: Dataset,
) -> None:
    if _snapshot_exists(db, workspace_id, "upload", upload.id):
        return
    metrics = build_metrics_payload(db, workspace_id)
    snap = WorkspaceTimelineSnapshot(
        workspace_id=workspace_id,
        event_type="upload",
        ref_id=upload.id,
        dataset_id=dataset.id,
        display_label=upload.filename or "Import",
        metrics_json=json.dumps(metrics),
        themes_json=None,
    )
    db.add(snap)
    db.commit()


def record_briefing_snapshot(
    db: Session,
    workspace_id: str,
    analysis: Analysis,
    result: dict[str, Any],
) -> None:
    if _snapshot_exists(db, workspace_id, "briefing", analysis.id):
        return
    metrics = build_metrics_payload(db, workspace_id)
    themes = themes_from_briefing_result(result)
    snap = WorkspaceTimelineSnapshot(
        workspace_id=workspace_id,
        event_type="briefing",
        ref_id=analysis.id,
        dataset_id=analysis.dataset_id,
        display_label="Workspace briefing",
        metrics_json=json.dumps(metrics),
        themes_json=json.dumps(themes),
    )
    db.add(snap)
    db.commit()


def record_append_snapshot(
    db: Session,
    workspace_id: str,
    dataset: Dataset,
    upload: Upload,
) -> None:
    metrics = build_metrics_payload(db, workspace_id)
    label = f"Rows added · {dataset.name}"
    snap = WorkspaceTimelineSnapshot(
        workspace_id=workspace_id,
        event_type="append",
        ref_id=upload.id,
        dataset_id=dataset.id,
        display_label=label[:512],
        metrics_json=json.dumps(metrics),
        themes_json=None,
    )
    db.add(snap)
    db.commit()


def _snapshot_exists(db: Session, workspace_id: str, event_type: str, ref_id: str) -> bool:
    return (
        db.query(WorkspaceTimelineSnapshot)
        .filter(
            WorkspaceTimelineSnapshot.workspace_id == workspace_id,
            WorkspaceTimelineSnapshot.event_type == event_type,
            WorkspaceTimelineSnapshot.ref_id == ref_id,
        )
        .first()
        is not None
    )


def list_snapshots(db: Session, workspace_id: str, limit: int = 40) -> list[WorkspaceTimelineSnapshot]:
    return (
        db.query(WorkspaceTimelineSnapshot)
        .filter(WorkspaceTimelineSnapshot.workspace_id == workspace_id)
        .order_by(WorkspaceTimelineSnapshot.created_at.desc())
        .limit(limit)
        .all()
    )


def serialize_snapshot(row: WorkspaceTimelineSnapshot) -> dict[str, Any]:
    metrics = json.loads(row.metrics_json) if row.metrics_json else {}
    themes = json.loads(row.themes_json) if row.themes_json else None
    return {
        "id": row.id,
        "event_type": row.event_type,
        "ref_id": row.ref_id,
        "dataset_id": row.dataset_id,
        "display_label": row.display_label,
        "metrics": metrics,
        "themes": themes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def compare_snapshots(
    a: dict[str, Any],
    b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two serialized snapshots' metrics (b = newer)."""
    ma = a.get("metrics") or {}
    mb = b.get("metrics") or {}
    ka = {
        f"{x.get('label')}|{x.get('dataset_name', '')}": x
        for x in (ma.get("kpis") or [])
    }
    kb = {
        f"{x.get('label')}|{x.get('dataset_name', '')}": x
        for x in (mb.get("kpis") or [])
    }
    keys = sorted(set(ka.keys()) & set(kb.keys()))
    diffs: list[dict[str, Any]] = []
    for key in keys:
        va = float(ka[key]["value"])
        vb = float(kb[key]["value"])
        if va == 0:
            continue
        pct = round(100.0 * (vb - va) / abs(va), 1)
        if abs(pct) < 0.5 and abs(vb - va) < 1e-6:
            continue
        diffs.append({
            "label": ka[key]["label"],
            "dataset_name": ka[key].get("dataset_name"),
            "previous_value": va,
            "current_value": vb,
            "delta_pct": pct,
            "direction": "up" if vb > va else "down" if vb < va else "flat",
        })
    diffs.sort(key=lambda x: -abs(x["delta_pct"]))
    row_a = int(ma.get("workspace_row_total") or 0)
    row_b = int(mb.get("workspace_row_total") or 0)
    row_delta = row_b - row_a
    return {
        "from_snapshot_id": a.get("id"),
        "to_snapshot_id": b.get("id"),
        "from_label": a.get("display_label"),
        "to_label": b.get("display_label"),
        "workspace_row_delta": row_delta,
        "workspace_row_previous": row_a,
        "workspace_row_current": row_b,
        "kpi_changes": diffs[:20],
    }


_BUCKET_LABELS = {
    "marketing_efficiency": "Marketing / spend efficiency",
    "margin_profit": "Margin or profit",
    "revenue_growth": "Revenue trajectory",
    "cost_pressure": "Cost pressure",
    "data_quality": "Data quality",
    "concentration": "Concentration / mix",
}


def compute_evolution(
    snapshots_chrono: list[dict[str, Any]],
) -> dict[str, Any]:
    """snapshots_chrono oldest → newest."""
    recurring: list[dict[str, Any]] = []
    improving: list[dict[str, Any]] = []

    briefing_snaps = [
        s for s in snapshots_chrono
        if s.get("event_type") == "briefing" and s.get("themes")
    ]
    if len(briefing_snaps) >= 3:
        window = briefing_snaps[-4:] if len(briefing_snaps) >= 4 else briefing_snaps
        bucket_counts: dict[str, int] = {}
        for s in window:
            buckets = (s.get("themes") or {}).get("buckets") or []
            for b in buckets:
                bucket_counts[b] = bucket_counts.get(b, 0) + 1
        n = len(window)
        for b, c in bucket_counts.items():
            if c >= 3 and n >= 3:
                recurring.append({
                    "theme_key": b,
                    "theme_label": _BUCKET_LABELS.get(b, b.replace("_", " ").title()),
                    "briefings_in_window": c,
                    "window_size": n,
                    "narrative": (
                        f"{_BUCKET_LABELS.get(b, b)} has shown up in {c} of the last {n} "
                        f"briefings—treat it as persistent, not a one-off."
                    ),
                })

    if len(snapshots_chrono) >= 2:
        prev_m = (snapshots_chrono[-2].get("metrics") or {})
        cur_m = (snapshots_chrono[-1].get("metrics") or {})
        pk = {f"{x.get('label')}|{x.get('dataset_name', '')}": x for x in (prev_m.get("kpis") or [])}
        ck = {f"{x.get('label')}|{x.get('dataset_name', '')}": x for x in (cur_m.get("kpis") or [])}
        seen_imp: set[str] = set()
        for key, cur in ck.items():
            if key not in pk:
                continue
            label = cur["label"]
            pv = float(pk[key]["value"])
            cv = float(cur["value"])
            if pv <= 0:
                continue
            pct = 100.0 * (cv - pv) / abs(pv)
            if _PROFIT_KPI.search(label) and pct >= 2 and "margin_profit" not in seen_imp:
                seen_imp.add("margin_profit")
                improving.append({
                    "theme_key": "margin_profit",
                    "narrative": (
                        f"{label} is up about {abs(pct):.1f}% vs your prior snapshot—"
                        f"confirm what changed before you bank the win."
                    ),
                })
            elif _REV_KPI.search(label) and pct >= 3 and "revenue_growth" not in seen_imp:
                seen_imp.add("revenue_growth")
                improving.append({
                    "theme_key": "revenue_growth",
                    "narrative": (
                        f"{label} moved up about {abs(pct):.1f}% vs the prior snapshot—"
                        f"check mix so growth is not a single-file artifact."
                    ),
                })

    return {"recurring": recurring[:6], "improving": improving[:4]}


def list_recent_digests(db: Session, workspace_id: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = (
        db.query(WorkspaceRecurringSummary)
        .filter(WorkspaceRecurringSummary.workspace_id == workspace_id)
        .order_by(WorkspaceRecurringSummary.period_start.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        content = json.loads(r.content_json) if r.content_json else {}
        out.append({
            "id": r.id,
            "kind": r.kind,
            "period_label": r.period_label,
            "headline": str(content.get("headline", ""))[:240],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out


def backfill_timeline_snapshots(db: Session) -> int:
    """Create missing upload/briefing snapshots for existing data. Returns rows added."""
    added = 0
    workspaces = [w.id for w in db.query(Workspace.id).all()]
    for wid in workspaces:
        uploads = (
            db.query(Upload)
            .filter(
                Upload.workspace_id == wid,
                Upload.status == UploadStatus.completed,
            )
            .order_by(Upload.created_at.asc())
            .all()
        )
        for up in uploads:
            if _snapshot_exists(db, wid, "upload", up.id):
                continue
            ds = db.query(Dataset).filter(Dataset.upload_id == up.id).first()
            if not ds:
                continue
            metrics = metrics_from_single_dataset(ds, up, quality="backfill")
            snap = WorkspaceTimelineSnapshot(
                workspace_id=wid,
                event_type="upload",
                ref_id=up.id,
                dataset_id=ds.id,
                display_label=up.filename or "Import",
                metrics_json=json.dumps(metrics),
                themes_json=None,
                created_at=up.created_at or datetime.utcnow(),
            )
            db.add(snap)
            added += 1
        analyses = (
            db.query(Analysis)
            .join(Dataset, Analysis.dataset_id == Dataset.id)
            .join(Upload, Dataset.upload_id == Upload.id)
            .filter(
                Analysis.type == "workspace_overview",
                Upload.workspace_id == wid,
            )
            .order_by(Analysis.created_at.asc())
            .all()
        )
        for an in analyses:
            if _snapshot_exists(db, wid, "briefing", an.id):
                continue
            try:
                result = json.loads(an.result_json) if an.result_json else {}
            except json.JSONDecodeError:
                result = {}
            metrics = build_metrics_payload(db, wid)
            metrics["snapshot_quality"] = "backfill"
            themes = themes_from_briefing_result(result) if result else None
            snap = WorkspaceTimelineSnapshot(
                workspace_id=wid,
                event_type="briefing",
                ref_id=an.id,
                dataset_id=an.dataset_id,
                display_label="Workspace briefing",
                metrics_json=json.dumps(metrics),
                themes_json=json.dumps(themes) if themes else None,
                created_at=an.created_at or datetime.utcnow(),
            )
            db.add(snap)
            added += 1
    if added:
        db.commit()
    return added
