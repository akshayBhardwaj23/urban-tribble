import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import require_active_workspace
from models.models import Dataset, Upload, UploadStatus, User
from services.column_detector import ColumnDetector
from services.dashboard_planner import DashboardPlanner
from services.data_cleaner import DataCleaner
from services.file_processor import FileProcessor
from services.ingestion_classifier import build_ingestion_profile

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

file_processor = FileProcessor()
data_cleaner = DataCleaner()
column_detector = ColumnDetector()
dashboard_planner = DashboardPlanner()


@router.post("/")
def create_upload(
    file: UploadFile = File(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported")

    upload = Upload(
        filename=file.filename or "unknown",
        file_type=ext,
        file_url="",
        user_description=description or None,
        status=UploadStatus.processing,
        workspace_id=workspace_id,
    )
    db.add(upload)
    db.flush()

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{upload.id}{ext}"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    upload.file_url = str(file_path)

    try:
        df = file_processor.read(str(file_path))
        df, clean_report = data_cleaner.clean(df)
        metadata = column_detector.detect(df)
        stats = column_detector.summary(df, metadata)
        plan = dashboard_planner.build_plan(
            df,
            metadata,
            stats,
            user_description=description or None,
        )
        ingestion = build_ingestion_profile(
            file.filename or "dataset",
            description or None,
            metadata,
            clean_report,
            list(df.columns),
        )
        cls_id = ingestion["classification"]["id"]

        upload.row_count = len(df)
        upload.column_count = len(df.columns)
        upload.status = UploadStatus.completed

        dataset = Dataset(
            upload_id=upload.id,
            name=file.filename or "dataset",
            schema_json=json.dumps(metadata),
            data_summary=json.dumps(stats),
            cleaned_report_json=json.dumps(clean_report),
            dashboard_plan_json=json.dumps(plan),
            business_classification=cls_id,
        )
        db.add(dataset)

        cleaned_path = upload_dir / f"{upload.id}_cleaned.parquet"
        df.to_parquet(str(cleaned_path), index=False)

    except Exception as e:
        upload.status = UploadStatus.failed
        db.commit()
        raise HTTPException(422, f"Failed to process file: {str(e)}")

    db.commit()
    db.refresh(upload)
    db.refresh(dataset)

    return {
        "id": upload.id,
        "filename": upload.filename,
        "file_type": upload.file_type,
        "status": upload.status.value,
        "user_description": upload.user_description,
        "dataset_id": dataset.id,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "cleaning_report": clean_report,
        "ingestion": ingestion,
        "all_columns": [str(c) for c in df.columns],
    }


@router.get("/{upload_id}")
def get_upload(upload_id: str, db: Session = Depends(get_db)):
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(404, "Upload not found")

    dataset = db.query(Dataset).filter(Dataset.upload_id == upload_id).first()

    return {
        "id": upload.id,
        "filename": upload.filename,
        "file_type": upload.file_type,
        "status": upload.status.value,
        "user_description": upload.user_description,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "created_at": upload.created_at.isoformat(),
        "dataset_id": dataset.id if dataset else None,
    }
