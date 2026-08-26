import contextlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import require_active_workspace
from models.models import Dataset, Upload, UploadStatus, User
from services import storage
from services.file_processor import FileProcessor
from services.file_validation import FileValidationError, validate_magic_bytes
from services.plan_limits import raise_plan_limit
from services.source_files import init_source_file
from services.subscription_usage import (
    assert_upload_allowed,
    get_effective_plan,
    remaining_upload_allowance,
)
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
        # Which tab this dataset actually read, and which of the workbook's
        # others are still unimported -- the review step offers those.
        "sheet": (_loads(dataset.mapping_spec_json) or {}).get("sheet") if dataset else None,
        "importable_sheets": sorted(
            {s["name"] for s in sheets}
            - (_imported_sheet_names(db, upload.workspace_id, upload) if sheets else set())
        ),
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


class ImportSheetsBody(BaseModel):
    # Each named tab becomes its own upload and its own dataset. Capped so a
    # workbook with a hundred tabs cannot be turned into a hundred datasets by
    # one request; the plan quota and the workspace limits apply on top.
    sheet_names: list[str] = Field(min_length=1, max_length=20)


@router.post("/{upload_id}/sheets")
def import_additional_sheets(
    upload_id: str,
    body: ImportSheetsBody,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Import further tabs of an already-uploaded workbook as separate datasets.

    A workbook whose tabs hold different datasets -- Jan/Feb/Mar, or one per
    region -- was previously reduced to whichever tab scored highest, and the
    only way to see another was to re-upload the file and switch tabs, which
    replaces the dataset rather than adding one.

    Each tab becomes its own upload so it gets its own dataset, dashboard and
    delete button. The bytes are copied per tab rather than shared: deleting a
    dataset deletes its sources, and a shared key would pull the file out from
    under its siblings.
    """
    user, workspace_id = ws
    upload = (
        db.query(Upload)
        .filter(Upload.id == upload_id, Upload.workspace_id == workspace_id)
        .first()
    )
    if not upload:
        raise HTTPException(404, "Upload not found")
    if upload.file_type not in (".xlsx", ".xls"):
        raise HTTPException(400, "Only Excel workbooks have sheets to import.")
    if upload.status != UploadStatus.completed:
        raise HTTPException(
            409, "This file is still being processed. Try again in a moment."
        )

    try:
        local = storage.materialize(upload.file_url)
    except Exception as exc:  # noqa: BLE001 — the bytes may have been cleaned up
        raise HTTPException(
            410, "The original file is no longer available. Upload it again."
        ) from exc

    available = {s["name"]: s for s in file_processor.list_sheets(str(local))}
    already = _imported_sheet_names(db, workspace_id, upload)

    wanted: list[str] = []
    for raw in body.sheet_names:
        name = (raw or "").strip()
        if not name or name in wanted:
            continue
        if name not in available:
            raise HTTPException(400, f'This workbook has no tab called "{name}".')
        if name in already:
            # Re-submitting the review step should not silently double a tab.
            continue
        wanted.append(name)

    if not wanted:
        return {"imported": 0, "uploads": [], "skipped_reason": "already imported"}

    check_upload_rate_limit(db, user.email)
    # The whole batch up front: creating three and failing on the fourth would
    # leave the user to work out which tabs landed.
    allowance = remaining_upload_allowance(db, user, workspace_id)
    if allowance is not None and len(wanted) > allowance:
        raise_plan_limit(
            get_effective_plan(db, user),
            "uploads",
            f"Importing {len(wanted)} sheet(s) would pass your plan's limit. "
            f"You can import {allowance} more.",
        )

    source_bytes = storage.read_bytes(upload.file_url)
    base = Path(upload.filename or "workbook").stem
    created: list[dict] = []

    for name in wanted:
        child = Upload(
            filename=f"{base} ({name}){upload.file_type}",
            file_type=upload.file_type,
            file_url="",
            user_description=upload.user_description,
            status=UploadStatus.pending,
            processing_stage="queued",
            workspace_id=workspace_id,
        )
        db.add(child)
        db.flush()

        key = storage.upload_key(child.id, upload.file_type)
        storage.write_bytes(key, source_bytes)
        init_source_file(
            child, key=key, filename=child.filename, kind="original"
        )
        child.status = UploadStatus.processing
        db.flush()
        created.append({"id": child.id, "filename": child.filename, "sheet": name})

    db.commit()

    for entry in created:
        if settings.UPLOAD_ASYNC_PROCESSING:
            enqueue(entry["id"], workspace_id, sheet_name=entry["sheet"])
        else:
            process_upload(entry["id"], workspace_id, sheet_name=entry["sheet"])

    return {
        "imported": len(created),
        "uploads": created,
        "skipped_reason": None,
    }


def _imported_sheet_names(db: Session, workspace_id: str, upload: Upload) -> set[str]:
    """Tabs of this workbook that already have a dataset in this workspace.

    Includes the tab the original upload itself read, which is why the worker
    records it -- otherwise the auto-picked tab would be offered again and
    imported twice.
    """
    names: set[str] = set()
    base = Path(upload.filename or "").stem
    siblings = (
        db.query(Upload)
        .filter(
            Upload.workspace_id == workspace_id,
            Upload.file_type == upload.file_type,
            Upload.status.in_((UploadStatus.completed, UploadStatus.processing)),
        )
        .all()
    )
    for row in siblings:
        if Path(row.filename or "").stem.split(" (")[0] != base.split(" (")[0]:
            continue
        dataset = db.query(Dataset).filter(Dataset.upload_id == row.id).first()
        if not dataset or not dataset.mapping_spec_json:
            continue
        spec = _loads(dataset.mapping_spec_json) or {}
        if spec.get("sheet"):
            names.add(str(spec["sheet"]))
    return names


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
