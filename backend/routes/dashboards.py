import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps import require_active_workspace
from models.models import Dataset, Upload, User
from services.workspace_query import (
    dataset_upload_pairs_for_workspace,
    get_dataset_upload_in_workspace,
)
from services.daily_metrics import (
    compute_daily_metrics_for_dataset,
    daily_metrics_to_records,
    resolve_date_column,
)
from services.dashboard_executor import (
    build_kpi_context_dict,
    daily_time_series_charts,
    execute_plan,
    fallback_ui_kpis,
    legacy_charts,
)
from services.period_change_summary import (
    build_what_changed_for_dataframe,
    build_workspace_what_changed,
    resolve_period_comparison_for_dataframe,
)
from services import overview_cache
from services.workspace_alerts import build_workspace_alerts
from services.workspace_query import latest_workspace_overview_analysis
from services.workspace_recommended_actions import build_recommended_actions
from services.workspace_habit_hints import build_workspace_habit_hints
from services.cleaned_parquet import CleanedDataMissingError, ensure_cleaned_parquet
from services.subscription_usage import (
    build_workspace_usage_payload,
    empty_what_changed,
    get_effective_plan,
    plan_features,
)

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _load_cleaned_df(upload: Upload) -> pd.DataFrame:
    try:
        parquet_path = ensure_cleaned_parquet(upload)
    except CleanedDataMissingError:
        raise HTTPException(404, "Cleaned data file not found")
    return pd.read_parquet(str(parquet_path))


def _parse_query_date(value: Optional[str]) -> Optional[pd.Timestamp]:
    if value is None or not str(value).strip():
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts).normalize()


def _filter_df_by_date_range(
    df: pd.DataFrame,
    date_col: str,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> pd.DataFrame:
    if start is None and end is None:
        return df
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    mask = parsed.notna()
    if start is not None:
        mask &= parsed.dt.normalize() >= start
    if end is not None:
        mask &= parsed.dt.normalize() <= end
    return df.loc[mask].copy()


@router.get("/dataset/{dataset_id}")
def get_dashboard_data(
    dataset_id: str,
    start_date: Optional[str] = Query(None, description="Inclusive start (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Inclusive end (YYYY-MM-DD)"),
    last_n_days: Optional[int] = Query(
        None,
        ge=1,
        le=366,
        description="Rolling window ending on the latest date in the file (overrides start/end)",
    ),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    row = get_dataset_upload_in_workspace(db, dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, upload = row

    df_full = _load_cleaned_df(upload)
    metadata = json.loads(dataset.schema_json) if dataset.schema_json else {}
    df = df_full

    date_bounds: dict[str, Optional[str]] = {"min": None, "max": None}
    _bounds_col = resolve_date_column(df_full, metadata)
    if _bounds_col and _bounds_col in df_full.columns:
        _bts = pd.to_datetime(df_full[_bounds_col], errors="coerce").dropna()
        if len(_bts) > 0:
            date_bounds = {
                "min": _bts.min().normalize().strftime("%Y-%m-%d"),
                "max": _bts.max().normalize().strftime("%Y-%m-%d"),
            }

    start_ts_explicit = _parse_query_date(start_date)
    end_ts_explicit = _parse_query_date(end_date)
    if (
        start_ts_explicit is not None
        and end_ts_explicit is not None
        and start_ts_explicit > end_ts_explicit
    ):
        start_ts_explicit, end_ts_explicit = end_ts_explicit, start_ts_explicit

    date_col = resolve_date_column(df_full, metadata)
    start_ts: Optional[pd.Timestamp] = None
    end_ts: Optional[pd.Timestamp] = None

    if last_n_days is not None and date_col and date_bounds["max"]:
        end_ts = _parse_query_date(date_bounds["max"])
        if end_ts is not None:
            start_ts = (
                end_ts - pd.Timedelta(days=int(last_n_days) - 1)
            ).normalize()
    elif start_ts_explicit is not None or end_ts_explicit is not None:
        start_ts, end_ts = start_ts_explicit, end_ts_explicit

    timeframe_requested = start_ts is not None or end_ts is not None
    feats_ds = plan_features(get_effective_plan(db, user))
    what_changed = (
        build_what_changed_for_dataframe(
            df_full,
            metadata,
            start_ts=start_ts if last_n_days is None else None,
            end_ts=end_ts if last_n_days is None else None,
            last_n_days=last_n_days,
        )
        if feats_ds["what_changed"]
        else empty_what_changed()
    )
    timeframe_applied = False
    active_start: Optional[str] = None
    active_end: Optional[str] = None
    if timeframe_requested and date_col:
        df = _filter_df_by_date_range(df_full, date_col, start_ts, end_ts)
        timeframe_applied = True
        if start_ts is not None:
            active_start = start_ts.strftime("%Y-%m-%d")
        if end_ts is not None:
            active_end = end_ts.strftime("%Y-%m-%d")

    timeframe_meta = {
        "applied": timeframe_applied,
        "start": active_start,
        "end": active_end,
        "date_column": date_col if timeframe_applied else None,
    }

    period_comparison = resolve_period_comparison_for_dataframe(
        df_full,
        metadata,
        start_ts=start_ts if last_n_days is None else None,
        end_ts=end_ts if last_n_days is None else None,
        last_n_days=last_n_days,
    )

    kpi_ctx = build_kpi_context_dict(
        source_file=dataset.name,
        row_count=len(df),
        timeframe_meta=timeframe_meta,
    )

    daily_df, daily_date_col, daily_revenue_col = compute_daily_metrics_for_dataset(
        df, metadata
    )
    daily_aggregates = (
        daily_metrics_to_records(daily_df) if daily_df is not None else []
    )

    plan = None
    if dataset.dashboard_plan_json:
        try:
            plan = json.loads(dataset.dashboard_plan_json)
        except json.JSONDecodeError:
            plan = None

    if plan and isinstance(plan.get("charts"), list) and len(plan["charts"]) > 0:
        kpis, charts = execute_plan(
            df,
            plan,
            daily_metrics=daily_df,
            date_col=daily_date_col,
            revenue_col=daily_revenue_col,
            kpi_context=kpi_ctx,
        )
        if not charts:
            charts = legacy_charts(
                df,
                metadata,
                daily_metrics=daily_df,
                primary_date=daily_date_col,
                primary_revenue=daily_revenue_col,
            )
        return {
            "dataset_id": dataset_id,
            "dataset_brief": plan.get("dataset_brief"),
            "dashboard_plan_source": plan.get("source"),
            "kpis": kpis,
            "charts": charts,
            "daily_aggregates": daily_aggregates,
            "timeframe": timeframe_meta,
            "date_bounds": date_bounds,
            "filtered_row_count": len(df),
            "what_changed": what_changed,
            "period_comparison": period_comparison,
        }

    charts = legacy_charts(
        df,
        metadata,
        daily_metrics=daily_df,
        primary_date=daily_date_col,
        primary_revenue=daily_revenue_col,
    )
    kpis = fallback_ui_kpis(df, metadata, kpi_context=kpi_ctx)
    return {
        "dataset_id": dataset_id,
        "dataset_brief": None,
        "dashboard_plan_source": "legacy",
        "kpis": kpis,
        "charts": charts,
        "daily_aggregates": daily_aggregates,
        "timeframe": timeframe_meta,
        "date_bounds": date_bounds,
        "filtered_row_count": len(df),
        "what_changed": what_changed,
        "period_comparison": period_comparison,
    }


@router.get("/overview")
def get_overview(
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Workspace-level overview aggregating data from all datasets."""
    user, workspace_id = ws
    plan = get_effective_plan(db, user)

    # Usage counters change on every action and are cheap, so they stay outside
    # the cache; the expensive parquet aggregation does not.
    usage_payload = build_workspace_usage_payload(db, user, workspace_id)
    payload = overview_cache.get_or_build(
        db,
        workspace_id,
        lambda: _build_overview(db, workspace_id, plan),
        extra_key=plan,
    )
    return {**payload, "usage": usage_payload}


def _build_overview(db: Session, workspace_id: str, plan: str) -> dict:
    all_datasets = dataset_upload_pairs_for_workspace(db, workspace_id).all()
    feats = plan_features(plan)

    if not all_datasets:
        return {
            "total_datasets": 0,
            "total_rows": 0,
            "kpis": [],
            "charts": [],
            "datasets": [],
            "what_changed": {
                "available": False,
                "period_description": "",
                "items": [],
                "highlights": [],
                "cross_metric_note": None,
            },
            "alerts": [],
            "recommended_actions": [],
            "habit_hints": build_workspace_habit_hints(
                db, workspace_id, has_datasets=False
            ),
            "plan_features": feats,
        }

    total_rows = sum(up.row_count or 0 for _, up in all_datasets)
    kpis = []
    all_charts = []
    # Only load parquet when a dataset lacks a precomputed overview series, or
    # when what_changed / alerts need the frame. Prefer the summary path.
    loaded_frames: dict[str, Any] = {}

    for ds, up in all_datasets:
        metadata = json.loads(ds.schema_json) if ds.schema_json else {}
        summary = json.loads(ds.data_summary) if ds.data_summary else {}

        primary_amount = metadata.get("primary_amount")
        revenue_cols_meta = list(metadata.get("revenue_columns", []) or [])
        # Prefer the primary amount only — listing every revenue column invited
        # users to add tiles that measure overlapping things.
        preferred = []
        if primary_amount and primary_amount in revenue_cols_meta:
            preferred = [primary_amount]
        elif revenue_cols_meta:
            preferred = [revenue_cols_meta[0]]
        for rev_col in preferred:
            total_key = f"{rev_col}_total"
            if total_key in summary:
                kpis.append({
                    "label": f"{rev_col.replace('_', ' ').title()}",
                    "value": summary[total_key],
                    "dataset_name": ds.name,
                    "dataset_id": ds.id,
                    "column": rev_col,
                    "is_primary_for_dataset": True,
                    "additive_across_sources": False,
                })

        series = summary.get("overview_series") or []
        period_comparison = None
        if series and isinstance(series, list) and len(series) >= 2:
            rev_label = (
                series[0].get("value_column")
                or (preferred[0] if preferred else "value")
            )
            all_charts.append({
                "id": f"{ds.id}_{rev_label}_over_time",
                "title": f"{str(rev_label).replace('_', ' ').title()} Over Time",
                "type": "line",
                "x_label": series[0].get("date_column") or "date",
                "y_label": rev_label,
                "data": [{"x": r["x"], "y": float(r["y"])} for r in series if "x" in r and "y" in r],
                "dataset_name": ds.name,
                "period_comparison": period_comparison,
                "from_summary": True,
            })
            continue

        try:
            df = _load_cleaned_df(up)
            loaded_frames[ds.id] = df
        except Exception:
            continue

        date_cols = metadata.get("date_columns", [])
        revenue_cols = metadata.get("revenue_columns", [])
        primary_t = metadata.get("primary_timeline")
        primary_a = metadata.get("primary_amount")
        if primary_t and primary_t in (date_cols or []):
            date_cols = [primary_t] + [c for c in date_cols if c != primary_t]
        if primary_a and primary_a in (revenue_cols or []):
            revenue_cols = [primary_a] + [c for c in revenue_cols if c != primary_a]
        elif primary_a and primary_a in df.columns:
            revenue_cols = [primary_a] + list(revenue_cols or [])
        category_cols = metadata.get("category_columns", [])

        period_comparison = resolve_period_comparison_for_dataframe(df, metadata)

        daily_df, _dcol, rcol = compute_daily_metrics_for_dataset(df, metadata)
        if daily_df is not None and rcol:
            dcharts = daily_time_series_charts(daily_df, rcol)
            if dcharts:
                ch = dcharts[0]
                all_charts.append({
                    "id": f"{ds.id}_{ch['id']}",
                    "title": ch["title"],
                    "type": ch["type"],
                    "x_label": ch.get("x_label"),
                    "y_label": ch.get("y_label"),
                    "data": ch["data"],
                    "dataset_name": ds.name,
                    "period_comparison": period_comparison,
                })
        else:
            for date_col in date_cols[:1]:
                for rev_col in revenue_cols[:1]:
                    if date_col in df.columns and rev_col in df.columns:
                        grouped = df.groupby(date_col)[rev_col].sum().reset_index()
                        grouped = grouped.sort_values(date_col)
                        chart_data = []
                        for _, row in grouped.iterrows():
                            val = row[date_col]
                            if pd.api.types.is_datetime64_any_dtype(type(val)):
                                val = val.strftime("%Y-%m-%d")
                            chart_data.append({"x": str(val), "y": float(row[rev_col])})

                        all_charts.append({
                            "id": f"{ds.id}_{rev_col}_over_{date_col}",
                            "title": f"{rev_col.replace('_', ' ').title()} Over Time",
                            "type": "line",
                            "x_label": date_col,
                            "y_label": rev_col,
                            "data": chart_data,
                            "dataset_name": ds.name,
                            "period_comparison": period_comparison,
                        })

        for cat_col in category_cols[:1]:
            for rev_col in revenue_cols[:1]:
                if cat_col in df.columns and rev_col in df.columns:
                    grouped = df.groupby(cat_col)[rev_col].sum().reset_index()
                    grouped = grouped.sort_values(rev_col, ascending=False).head(10)
                    chart_data = [
                        {"name": str(row[cat_col]), "value": float(row[rev_col])}
                        for _, row in grouped.iterrows()
                    ]
                    all_charts.append({
                        "id": f"{ds.id}_{rev_col}_by_{cat_col}",
                        "title": f"{rev_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
                        "type": "bar",
                        "data": chart_data,
                        "dataset_name": ds.name,
                    })

    def _loader(upload):
        # Prefer a frame already loaded for charts; otherwise open parquet once.
        for ds, up in all_datasets:
            if up.id == upload.id and ds.id in loaded_frames:
                return loaded_frames[ds.id]
        return _load_cleaned_df(upload)

    what_changed = (
        build_workspace_what_changed(all_datasets, _loader)
        if feats["what_changed"]
        else empty_what_changed()
    )
    analysis = latest_workspace_overview_analysis(db, workspace_id)
    analysis_obj = None
    if analysis and analysis.result_json:
        try:
            analysis_obj = json.loads(analysis.result_json)
        except json.JSONDecodeError:
            analysis_obj = None
    alerts = (
        build_workspace_alerts(
            what_changed,
            all_datasets,
            _loader,
            analysis_obj,
        )
        if feats["alerts"]
        else []
    )
    recommended_actions = build_recommended_actions(
        analysis_obj,
        alerts,
        what_changed,
    )
    if plan == "free":
        recommended_actions = recommended_actions[:2]
    habit_hints = build_workspace_habit_hints(
        db, workspace_id, has_datasets=True
    )

    datasets_list = []
    for ds, up in all_datasets:
        metadata = json.loads(ds.schema_json) if ds.schema_json else {}
        date_cols = metadata.get("date_columns", []) or []
        rev = metadata.get("revenue_columns", []) or []
        num = metadata.get("numeric_columns", []) or []
        value_opts: list[str] = []
        for c in rev + num:
            if c and c not in value_opts:
                value_opts.append(c)
        datasets_list.append({
            "id": ds.id,
            "name": ds.name,
            "row_count": up.row_count,
            "column_count": up.column_count,
            "created_at": ds.created_at.isoformat(),
            "date_columns": date_cols,
            "value_columns": value_opts,
        })

    shown_kpis = kpis[:8]
    sources_with_revenue = len({k["dataset_id"] for k in shown_kpis})

    return {
        "total_datasets": len(all_datasets),
        "total_rows": total_rows,
        "kpis": shown_kpis,
        "kpi_note": (
            f"Each figure is one column from one source ({sources_with_revenue} sources). "
            "Sources measure overlapping things, so these do not add up to company revenue."
            if sources_with_revenue > 1
            else None
        ),
        "charts": all_charts[:6],
        "datasets": datasets_list,
        "what_changed": what_changed,
        "alerts": alerts,
        "recommended_actions": recommended_actions,
        "habit_hints": habit_hints,
        "plan_features": feats,
    }
