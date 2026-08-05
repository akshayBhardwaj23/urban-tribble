"""Background processing for uploads.

Parsing, cleaning and the LLM planning pass used to run inline on an async
endpoint, so one large workbook blocked the event loop for every other request.
The request now only stores bytes and returns; a bounded worker pool does the
rest and records progress on the Upload row for polling.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from config import settings
from database import SessionLocal
from models.models import Dataset, Upload, UploadStatus
from services import storage
from services.cleaned_parquet import write_cleaned_parquet
from services.dashboard_planner import DashboardPlanner
from services.file_processor import FileProcessor
from services.file_validation import FileValidationError, validate_frame_size
from services.ingest_pipeline import process_dataframe
from services.workspace_timeline import record_upload_snapshot

logger = logging.getLogger(__name__)

_executor: Optional[ThreadPoolExecutor] = None
_file_processor = FileProcessor()
_dashboard_planner = DashboardPlanner()

STAGES = ("queued", "reading", "cleaning", "profiling", "planning", "saving")


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=max(1, int(settings.UPLOAD_WORKER_THREADS)),
            thread_name_prefix="upload",
        )
    return _executor


def shutdown_executor() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


def enqueue(upload_id: str, workspace_id: str) -> None:
    get_executor().submit(_run_safely, upload_id, workspace_id)


def _run_safely(upload_id: str, workspace_id: str) -> None:
    try:
        process_upload(upload_id, workspace_id)
    except Exception:  # noqa: BLE001 — worker threads must never raise
        logger.exception("upload %s failed in background worker", upload_id)


def _set_stage(db, upload: Upload, stage: str) -> None:
    upload.processing_stage = stage
    db.commit()


def process_upload(upload_id: str, workspace_id: str) -> None:
    """Parse, clean, profile and persist one upload. Safe to call synchronously."""
    db = SessionLocal()
    try:
        upload = db.query(Upload).filter(Upload.id == upload_id).first()
        if upload is None:
            logger.warning("upload %s vanished before processing", upload_id)
            return

        source_key = upload.file_url
        try:
            _set_stage(db, upload, "reading")
            local = storage.materialize(source_key)
            df = _file_processor.read(str(local))
            validate_frame_size(df, filename=upload.filename)

            _set_stage(db, upload, "cleaning")
            processed = process_dataframe(
                df,
                filename=upload.filename or "dataset",
                description=upload.user_description,
            )
            df = processed["df"]
            validate_frame_size(df, filename=upload.filename)

            _set_stage(db, upload, "planning")
            plan = _dashboard_planner.build_plan(
                df,
                processed["metadata"],
                processed["stats"],
                user_description=upload.user_description,
            )

            _set_stage(db, upload, "saving")
            dataset = db.query(Dataset).filter(Dataset.upload_id == upload.id).first()
            if dataset is None:
                dataset = Dataset(upload_id=upload.id, name=upload.filename or "dataset")
                db.add(dataset)

            dataset.name = upload.filename or "dataset"
            dataset.schema_json = json.dumps(processed["metadata"])
            dataset.data_summary = json.dumps(processed["stats"])
            dataset.cleaned_report_json = json.dumps(processed["clean_report"])
            dataset.dashboard_plan_json = json.dumps(plan)
            dataset.business_classification = processed["ingestion"]["classification"]["id"]
            dataset.mapping_spec_json = json.dumps(processed["mapping_spec"])

            write_cleaned_parquet(upload, df)

            upload.row_count = len(df)
            upload.column_count = len(df.columns)
            upload.status = UploadStatus.completed
            upload.processing_stage = None
            upload.processing_error = None
            db.commit()

            try:
                record_upload_snapshot(db, workspace_id, upload, dataset)
            except Exception:  # noqa: BLE001 — timeline is best-effort
                logger.info("timeline snapshot skipped for upload %s", upload.id)

        except Exception as exc:  # noqa: BLE001 — record failure, then clean up
            db.rollback()
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if upload is not None:
                upload.status = UploadStatus.failed
                upload.processing_stage = None
                upload.processing_error = _user_message(exc)
                db.commit()
            # A failed upload keeps no bytes: the file is unusable and would
            # otherwise sit in storage forever.
            storage.delete(source_key)
            logger.warning("upload %s failed: %s", upload_id, exc)
    finally:
        db.close()


def _user_message(exc: Exception) -> str:
    if isinstance(exc, FileValidationError):
        return str(exc)
    text = str(exc).strip()
    if not text:
        return "We couldn't read this file. Check that it opens in Excel and try again."
    return f"We couldn't process this file: {text[:400]}"
