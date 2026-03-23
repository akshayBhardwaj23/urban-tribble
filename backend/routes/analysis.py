from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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
    periods: int = 12


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
