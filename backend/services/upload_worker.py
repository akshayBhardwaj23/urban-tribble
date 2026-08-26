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

_executor: ThreadPoolExecutor | None = None
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


def enqueue(upload_id: str, workspace_id: str, sheet_name: str | None = None) -> None:
    get_executor().submit(_run_safely, upload_id, workspace_id, sheet_name)


def _run_safely(
    upload_id: str, workspace_id: str, sheet_name: str | None = None
) -> None:
    try:
        process_upload(upload_id, workspace_id, sheet_name=sheet_name)
    except Exception:  # noqa: BLE001 — worker threads must never raise
        logger.exception("upload %s failed in background worker", upload_id)


def resolve_sheet(local_path: str, sheet_name: str | None) -> tuple[str | None, int | None]:
    """Which tab to read, and the header row that goes with it.

    ``FileProcessor.read`` auto-picks the most table-like tab when given no
    name, but does not say which one it chose -- so the dataset could never
    record where its rows came from, and nothing could tell which tabs of a
    workbook were still unimported.

    ``list_sheets`` scores and sorts by exactly the same rule, so its first
    entry *is* that auto-pick. Naming it explicitly also means passing the
    header row along: ``read`` only runs its own header detection on the
    auto-pick path, and would otherwise silently fall back to row 0 the moment
    a sheet is named.
    """
    sheets = _file_processor.list_sheets(local_path)
    if not sheets:
        # CSV/TSV, or a workbook whose tabs could not be listed.
        return None, None
    by_name = {s["name"]: s for s in sheets}
    entry = by_name.get(sheet_name) if sheet_name else sheets[0]
    if entry is None:
        raise FileValidationError(
            f'This file has no tab called "{sheet_name}".'
        )
    return entry["name"], entry.get("suggested_header_row")


def _set_stage(db, upload: Upload, stage: str) -> None:
    upload.processing_stage = stage
    db.commit()


def process_upload(
    upload_id: str, workspace_id: str, sheet_name: str | None = None
) -> None:
    """Parse, clean, profile and persist one upload. Safe to call synchronously.

    ``sheet_name`` names the tab to read; without it the most table-like tab is
    used, which is what a plain single-file upload does.
    """
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
            chosen_sheet, header_row = resolve_sheet(str(local), sheet_name)
            df = _file_processor.read(
                str(local), sheet_name=chosen_sheet, header_row=header_row
            )
            validate_frame_size(df, filename=upload.filename)

            _set_stage(db, upload, "cleaning")
            processed = process_dataframe(
                df,
                filename=upload.filename or "dataset",
                description=upload.user_description,
                # Recorded on the mapping spec so the dataset knows which tab
                # it came from; it read as None for every upload before this.
                sheet=chosen_sheet,
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
