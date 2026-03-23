import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.models import Dataset, Upload

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _load_cleaned_df(upload: Upload) -> pd.DataFrame:
    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")
    return pd.read_parquet(str(parquet_path))


@router.get("/")
def list_datasets(db: Session = Depends(get_db)):
    datasets = (
        db.query(Dataset, Upload)
        .join(Upload, Dataset.upload_id == Upload.id)
        .order_by(Dataset.created_at.desc())
        .all()
    )
    return [
        {
            "id": ds.id,
            "name": ds.name,
            "upload_id": ds.upload_id,
            "row_count": up.row_count,
            "column_count": up.column_count,
            "status": up.status.value,
            "user_description": up.user_description,
            "created_at": ds.created_at.isoformat(),
        }
        for ds, up in datasets
    ]


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    return {
        "id": dataset.id,
        "upload_id": dataset.upload_id,
        "name": dataset.name,
        "schema_json": json.loads(dataset.schema_json) if dataset.schema_json else None,
        "data_summary": json.loads(dataset.data_summary) if dataset.data_summary else None,
        "cleaned_report": json.loads(dataset.cleaned_report_json) if dataset.cleaned_report_json else None,
        "created_at": dataset.created_at.isoformat(),
    }


@router.get("/{dataset_id}/preview")
def get_preview(
    dataset_id: str,
    n: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    upload = db.query(Upload).filter(Upload.id == dataset.upload_id).first()
    if not upload:
        raise HTTPException(404, "Upload not found")

    df = _load_cleaned_df(upload)

    preview = df.head(n)
    for col in preview.columns:
        if pd.api.types.is_datetime64_any_dtype(preview[col]):
            preview[col] = preview[col].dt.strftime("%Y-%m-%d")

    return {
        "columns": list(df.columns),
        "rows": preview.where(preview.notna(), None).to_dict(orient="records"),
        "total_rows": len(df),
        "total_columns": len(df.columns),
    }
