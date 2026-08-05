import contextlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import require_active_workspace
from models.models import Dataset, Upload, UploadStatus, User
from services import storage
from services.file_processor import FileProcessor
from services.file_validation import FileValidationError, validate_magic_bytes
from services.source_files import init_source_file
from services.subscription_usage import assert_upload_allowed
from services.upload_io import save_upload_stream_limited
from services.upload_rate_limit import check_upload_rate_limit
from services.upload_worker import enqueue, process_upload

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

file_processor = FileProcessor()


@router.post("/")
async def create_upload(
    file: UploadFile = File(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    check_upload_rate_limit(db, user.email)
    assert_upload_allowed(db, user, workspace_id)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported")

    upload = Upload(
        filename=file.filename or "unknown",
        file_type=ext,
        file_url="",
        user_description=description or None,
        status=UploadStatus.pending,
        processing_stage="queued",
        workspace_id=workspace_id,
    )
    db.add(upload)
    db.flush()

    key = storage.upload_key(upload.id, ext)
    staging = Path(settings.UPLOAD_DIR) / ".incoming" / f"{upload.id}{ext}"
    staging.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    ok = await save_upload_stream_limited(file, staging, max_bytes)
    if not ok:
        db.delete(upload)
        db.commit()
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
        )

    try:
        validate_magic_bytes(staging, ext)
    except FileValidationError as exc:
        staging.unlink(missing_ok=True)
        db.delete(upload)
        db.commit()
        raise HTTPException(400, str(exc)) from exc

    try:
        storage.upload_file(staging, key)
    except Exception as exc:  # noqa: BLE001 — storage outage should not orphan a row
        staging.unlink(missing_ok=True)
        db.delete(upload)
        db.commit()
        raise HTTPException(503, "Storage is unavailable right now. Try again shortly.") from exc

    init_source_file(
        upload,
        key=key,
        filename=file.filename or "unknown",
        kind="original",
    )
    upload.status = UploadStatus.processing
    db.commit()

    if settings.UPLOAD_ASYNC_PROCESSING:
        enqueue(upload.id, workspace_id)
        db.refresh(upload)
        return _pending_payload(upload)

    process_upload(upload.id, workspace_id)
    db.expire_all()
    upload = db.query(Upload).filter(Upload.id == upload.id).first()
    if upload is None or upload.status == UploadStatus.failed:
        detail = (upload.processing_error if upload else None) or "Failed to process file"
        raise HTTPException(422, detail)
    return _completed_payload(db, upload)


def _pending_payload(upload: Upload) -> dict:
    return {
        "id": upload.id,
        "filename": upload.filename,
        "file_type": upload.file_type,
        "status": upload.status.value,
        "processing_stage": upload.processing_stage,
        "user_description": upload.user_description,
        "dataset_id": None,
        "row_count": None,
        "column_count": None,
        "poll_url": f"/api/uploads/{upload.id}",
    }


def _completed_payload(db: Session, upload: Upload) -> dict:
    dataset = db.query(Dataset).filter(Dataset.upload_id == upload.id).first()
    sheets = []
    if upload.file_type in (".xlsx", ".xls") and upload.file_url:
        with contextlib.suppress(Exception):
            sheets = file_processor.list_sheets(str(storage.materialize(upload.file_url)))

    return {
        "id": upload.id,
        "filename": upload.filename,
        "file_type": upload.file_type,
        "status": upload.status.value,
        "processing_stage": upload.processing_stage,
        "user_description": upload.user_description,
        "dataset_id": dataset.id if dataset else None,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "cleaning_report": _loads(dataset.cleaned_report_json) if dataset else None,
        "ingestion": _ingestion_from(dataset),
        "mapping_spec": _loads(dataset.mapping_spec_json) if dataset else None,
        "all_columns": (_loads(dataset.schema_json) or {}).get("all_columns", []) if dataset else [],
        "sheets": sheets,
    }


def _loads(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _ingestion_from(dataset):
    spec = _loads(dataset.mapping_spec_json) if dataset else None
    return (spec or {}).get("ingestion_profile")


@router.get("/{upload_id}")
def get_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    upload = (
        db.query(Upload)
        .filter(Upload.id == upload_id, Upload.workspace_id == workspace_id)
        .first()
    )
    if not upload:
        raise HTTPException(404, "Upload not found")

    if upload.status == UploadStatus.completed:
        payload = _completed_payload(db, upload)
    else:
        payload = _pending_payload(upload)
        payload["error"] = upload.processing_error

    payload["created_at"] = upload.created_at.isoformat()
    return payload
