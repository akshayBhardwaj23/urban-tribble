import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.models import Dataset, Upload
from services.daily_metrics import (
    compute_daily_metrics_for_dataset,
    daily_metrics_to_records,
    resolve_date_column,
)
from services.dashboard_executor import (
    daily_time_series_charts,
    execute_plan,
    fallback_ui_kpis,
    legacy_charts,
)

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _load_cleaned_df(upload: Upload) -> pd.DataFrame:
    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
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
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    upload = db.query(Upload).filter(Upload.id == dataset.upload_id).first()
    if not upload:
        raise HTTPException(404, "Upload not found")

    df = _load_cleaned_df(upload)
    metadata = json.loads(dataset.schema_json) if dataset.schema_json else {}

    date_bounds: dict[str, Optional[str]] = {"min": None, "max": None}
    _bounds_col = resolve_date_column(df, metadata)
    if _bounds_col and _bounds_col in df.columns:
        _bts = pd.to_datetime(df[_bounds_col], errors="coerce").dropna()
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

    date_col = resolve_date_column(df, metadata)
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
    timeframe_applied = False
    active_start: Optional[str] = None
    active_end: Optional[str] = None
    if timeframe_requested and date_col:
        df = _filter_df_by_date_range(df, date_col, start_ts, end_ts)
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
        }

    charts = legacy_charts(
        df,
        metadata,
        daily_metrics=daily_df,
        primary_date=daily_date_col,
        primary_revenue=daily_revenue_col,
    )
    kpis = fallback_ui_kpis(df, metadata)
    return {
        "dataset_id": dataset_id,
        "dataset_brief": None,
        "dashboard_plan_source": "legacy",
        "kpis": kpis,
        "charts": charts,
        "daily_aggregates": daily_aggregates,
        "timeframe": timeframe_meta,
        "date_bounds": date_bounds,
    }


@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    """Workspace-level overview aggregating data from all datasets."""
    all_datasets = (
        db.query(Dataset, Upload)
        .join(Upload, Dataset.upload_id == Upload.id)
        .order_by(Dataset.created_at.desc())
        .all()
    )

    if not all_datasets:
        return {
            "total_datasets": 0,
            "total_rows": 0,
            "kpis": [],
            "charts": [],
            "datasets": [],
        }

    total_rows = sum(up.row_count or 0 for _, up in all_datasets)
    kpis = []
    all_charts = []

    for ds, up in all_datasets:
        metadata = json.loads(ds.schema_json) if ds.schema_json else {}
        summary = json.loads(ds.data_summary) if ds.data_summary else {}

        for rev_col in metadata.get("revenue_columns", []):
            total_key = f"{rev_col}_total"
            if total_key in summary:
                kpis.append({
                    "label": f"{rev_col.replace('_', ' ').title()}",
                    "value": summary[total_key],
                    "dataset_name": ds.name,
                })

        try:
            df = _load_cleaned_df(up)
        except Exception:
            continue

        date_cols = metadata.get("date_columns", [])
        revenue_cols = metadata.get("revenue_columns", [])
        category_cols = metadata.get("category_columns", [])

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

    datasets_list = [
        {
            "id": ds.id,
            "name": ds.name,
            "row_count": up.row_count,
            "column_count": up.column_count,
            "created_at": ds.created_at.isoformat(),
        }
        for ds, up in all_datasets
    ]

    return {
        "total_datasets": len(all_datasets),
        "total_rows": total_rows,
        "kpis": kpis[:8],
        "charts": all_charts[:6],
        "datasets": datasets_list,
    }
