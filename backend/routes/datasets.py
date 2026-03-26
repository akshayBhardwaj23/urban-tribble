import json
import shutil
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.models import Analysis, ChatMessage, Dataset, DatasetRelation, Upload
from services.column_detector import ColumnDetector
from services.data_cleaner import DataCleaner
from services.file_processor import FileProcessor

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


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    upload = db.query(Upload).filter(Upload.id == dataset.upload_id).first()

    db.query(ChatMessage).filter(ChatMessage.dataset_id == dataset_id).delete()
    db.query(Analysis).filter(Analysis.dataset_id == dataset_id).delete()
    db.query(DatasetRelation).filter(
        (DatasetRelation.source_dataset_id == dataset_id)
        | (DatasetRelation.target_dataset_id == dataset_id)
    ).delete(synchronize_session="fetch")

    db.delete(dataset)

    if upload:
        original = Path(upload.file_url)
        if original.exists():
            original.unlink()
        parquet = original.parent / f"{upload.id}_cleaned.parquet"
        if parquet.exists():
            parquet.unlink()
        db.delete(upload)

    db.commit()
    return {"status": "deleted", "dataset_id": dataset_id}


file_processor = FileProcessor()
data_cleaner = DataCleaner()
column_detector = ColumnDetector()


@router.post("/{dataset_id}/append")
def append_to_dataset(
    dataset_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    upload = db.query(Upload).filter(Upload.id == dataset.upload_id).first()
    if not upload:
        raise HTTPException(404, "Upload not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported")

    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")

    df_existing = pd.read_parquet(str(parquet_path))

    upload_dir = Path(settings.UPLOAD_DIR)
    tmp_path = upload_dir / f"tmp_append_{dataset_id}{ext}"
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        df_new = file_processor.read(str(tmp_path))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    existing_cols = set(c.lower() for c in df_existing.columns)
    new_cols = set(c.lower() for c in df_new.columns)
    overlap = existing_cols & new_cols

    if len(overlap) < len(existing_cols) * 0.5:
        raise HTTPException(
            400,
            f"Column mismatch: new file shares only {len(overlap)} of "
            f"{len(existing_cols)} columns. Files may not be compatible.",
        )

    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    df_combined, clean_report = data_cleaner.clean(df_combined)
    metadata = column_detector.detect(df_combined)
    stats = column_detector.summary(df_combined, metadata)

    df_combined.to_parquet(str(parquet_path), index=False)

    upload.row_count = len(df_combined)
    upload.column_count = len(df_combined.columns)

    dataset.schema_json = json.dumps(metadata)
    dataset.data_summary = json.dumps(stats)
    dataset.cleaned_report_json = json.dumps(clean_report)

    db.commit()
    db.refresh(dataset)

    return {
        "dataset_id": dataset.id,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "cleaning_report": clean_report,
    }
