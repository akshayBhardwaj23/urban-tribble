from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.models import Analysis, Dataset, Upload
from services.ai_analyzer import AIAnalyzer
from services.forecaster import Forecaster

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

ai_analyzer = AIAnalyzer()
forecaster = Forecaster()


class RunAnalysisRequest(BaseModel):
    dataset_id: str


class ForecastRequest(BaseModel):
    dataset_id: str
    date_column: Optional[str] = None
    value_column: Optional[str] = None
    periods: int = Field(default=90, ge=1, le=366)


@router.post("/run")
def run_analysis(req: RunAnalysisRequest, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    upload = db.query(Upload).filter(Upload.id == dataset.upload_id).first()

    data_summary = json.loads(dataset.data_summary) if dataset.data_summary else {}
    column_metadata = json.loads(dataset.schema_json) if dataset.schema_json else {}
    user_description = upload.user_description if upload else None

    result = ai_analyzer.analyze(data_summary, column_metadata, user_description)

    analysis = Analysis(
        dataset_id=dataset.id,
        type="overview",
        result_json=json.dumps(result),
        ai_summary=result.get("executive_summary", ""),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return {
        "id": analysis.id,
        "dataset_id": analysis.dataset_id,
        "type": analysis.type,
        "result_json": result,
        "ai_summary": analysis.ai_summary,
        "created_at": analysis.created_at.isoformat(),
    }


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    return {
        "id": analysis.id,
        "dataset_id": analysis.dataset_id,
        "type": analysis.type,
        "result_json": json.loads(analysis.result_json) if analysis.result_json else None,
        "ai_summary": analysis.ai_summary,
        "created_at": analysis.created_at.isoformat(),
    }


@router.get("/dataset/{dataset_id}")
def get_analysis_by_dataset(dataset_id: str, db: Session = Depends(get_db)):
    analysis = (
        db.query(Analysis)
        .filter(Analysis.dataset_id == dataset_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )
    if not analysis:
        return None

    return {
        "id": analysis.id,
        "dataset_id": analysis.dataset_id,
        "type": analysis.type,
        "result_json": json.loads(analysis.result_json) if analysis.result_json else None,
        "ai_summary": analysis.ai_summary,
        "created_at": analysis.created_at.isoformat(),
    }


@router.post("/forecast")
def run_forecast(req: ForecastRequest, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    upload = db.query(Upload).filter(Upload.id == dataset.upload_id).first()
    if not upload:
        raise HTTPException(404, "Upload not found")

    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")

    df = pd.read_parquet(str(parquet_path))
    schema = json.loads(dataset.schema_json) if dataset.schema_json else {}

    date_col = req.date_column or (schema.get("date_columns", [None]) or [None])[0]
    value_col = req.value_column or (schema.get("revenue_columns", [None]) or [None])[0]

    if not date_col or not value_col:
        raise HTTPException(
            400, "Could not auto-detect date and value columns. Please specify them."
        )

    try:
        result = forecaster.forecast(df, date_col, value_col, req.periods)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "dataset_id": dataset.id,
        "date_column": date_col,
        "value_column": value_col,
        **result,
    }


@router.post("/overview/run")
def run_overview_analysis(db: Session = Depends(get_db)):
    """AI analysis across all datasets in the workspace."""
    all_datasets = (
        db.query(Dataset, Upload)
        .join(Upload, Dataset.upload_id == Upload.id)
        .all()
    )
    if not all_datasets:
        raise HTTPException(404, "No datasets found")

    combined_summary: dict = {"datasets": []}
    combined_metadata: dict = {
        "date_columns": [], "revenue_columns": [],
        "category_columns": [], "numeric_columns": [], "text_columns": [],
    }

    for ds, up in all_datasets:
        meta = json.loads(ds.schema_json) if ds.schema_json else {}
        summ = json.loads(ds.data_summary) if ds.data_summary else {}
        combined_summary["datasets"].append({
            "name": ds.name,
            "description": up.user_description,
            "rows": up.row_count,
            "columns": up.column_count,
            "summary": summ,
        })
        for key in combined_metadata:
            combined_metadata[key].extend(meta.get(key, []))

    combined_summary["total_datasets"] = len(all_datasets)
    combined_summary["total_rows"] = sum(up.row_count or 0 for _, up in all_datasets)

    result = ai_analyzer.analyze(
        combined_summary, combined_metadata,
        f"Workspace with {len(all_datasets)} business datasets",
    )

    first_ds = all_datasets[0][0]
    analysis = Analysis(
        dataset_id=first_ds.id,
        type="workspace_overview",
        result_json=json.dumps(result),
        ai_summary=result.get("executive_summary", ""),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return {
        "id": analysis.id,
        "type": analysis.type,
        "result_json": result,
        "ai_summary": analysis.ai_summary,
        "created_at": analysis.created_at.isoformat(),
    }


@router.get("/overview/latest")
def get_overview_analysis(db: Session = Depends(get_db)):
    """Get the most recent workspace-level analysis."""
    analysis = (
        db.query(Analysis)
        .filter(Analysis.type == "workspace_overview")
        .order_by(Analysis.created_at.desc())
        .first()
    )
    if not analysis:
        return None

    return {
        "id": analysis.id,
        "type": analysis.type,
        "result_json": json.loads(analysis.result_json) if analysis.result_json else None,
        "ai_summary": analysis.ai_summary,
        "created_at": analysis.created_at.isoformat(),
    }


class OverviewForecastRequest(BaseModel):
    """Forward steps at the inferred data frequency (day / week / month)."""
    periods: int = Field(default=90, ge=1, le=366)


@router.post("/overview/forecast")
def run_overview_forecast(
    req: OverviewForecastRequest,
    db: Session = Depends(get_db),
):
    """Forecast using the best date+revenue pair found across all datasets.

    Chooses the dataset with the most rows that has at least one date column and
    one revenue/numeric column, then uses the *first* date column and *first*
    revenue column from that file's schema.
    """
    all_datasets = (
        db.query(Dataset, Upload)
        .join(Upload, Dataset.upload_id == Upload.id)
        .all()
    )

    best_ds = None
    best_up = None
    best_date_col = None
    best_value_col = None
    best_rows = 0

    for ds, up in all_datasets:
        schema = json.loads(ds.schema_json) if ds.schema_json else {}
        date_cols = schema.get("date_columns", [])
        rev_cols = schema.get("revenue_columns", [])
        if date_cols and rev_cols and (up.row_count or 0) > best_rows:
            best_ds = ds
            best_up = up
            best_date_col = date_cols[0]
            best_value_col = rev_cols[0]
            best_rows = up.row_count or 0

    if not best_ds or not best_up or not best_date_col or not best_value_col:
        raise HTTPException(
            400, "No dataset with both date and revenue columns found for forecasting."
        )

    parquet_path = Path(best_up.file_url).parent / f"{best_up.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")

    df = pd.read_parquet(str(parquet_path))

    try:
        result = forecaster.forecast(df, best_date_col, best_value_col, req.periods)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "dataset_id": best_ds.id,
        "dataset_name": best_ds.name,
        "date_column": best_date_col,
        "value_column": best_value_col,
        **result,
    }
