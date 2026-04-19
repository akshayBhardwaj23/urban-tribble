import json
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import require_active_workspace
from models.models import (
    Analysis,
    ChatMessage,
    Dataset,
    DatasetRelation,
    Upload,
    User,
    Workspace,
    WorkspaceTimelineSnapshot,
)
from services.workspace_query import (
    dataset_upload_pairs_for_workspace,
    get_dataset_upload_in_workspace,
)
from services.ingestion_classifier import ALLOWED_CLASSIFICATION_IDS, CLASSIFICATIONS
from services.column_detector import ColumnDetector
from services.dashboard_planner import DashboardPlanner
from services.data_cleaner import DataCleaner
from services.file_processor import FileProcessor
from services.upload_io import save_upload_stream_limited
from services.upload_rate_limit import check_upload_rate_limit
from services.workspace_timeline import record_append_snapshot

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

dashboard_planner = DashboardPlanner()
column_detector = ColumnDetector()


class DatasetPatchBody(BaseModel):
    business_classification: Optional[str] = None
    primary_date_column: Optional[str] = None
    primary_amount_column: Optional[str] = None
    segment_columns: Optional[List[str]] = None


def _load_cleaned_df(upload: Upload) -> pd.DataFrame:
    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")
    return pd.read_parquet(str(parquet_path))


@router.get("/")
def list_datasets(
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    datasets = dataset_upload_pairs_for_workspace(db, workspace_id).all()
    return [
        {
            "id": ds.id,
            "name": ds.name,
            "upload_id": ds.upload_id,
            "row_count": up.row_count,
            "column_count": up.column_count,
            "status": up.status.value,
            "user_description": up.user_description,
            "business_classification": ds.business_classification,
            "created_at": ds.created_at.isoformat(),
        }
        for ds, up in datasets
    ]


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    row = get_dataset_upload_in_workspace(db, dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, _upload = row

    return {
        "id": dataset.id,
        "upload_id": dataset.upload_id,
        "name": dataset.name,
        "schema_json": json.loads(dataset.schema_json) if dataset.schema_json else None,
        "data_summary": json.loads(dataset.data_summary) if dataset.data_summary else None,
        "cleaned_report": json.loads(dataset.cleaned_report_json) if dataset.cleaned_report_json else None,
        "business_classification": dataset.business_classification,
        "created_at": dataset.created_at.isoformat(),
    }


def _rebuild_after_schema_edit(
    dataset: Dataset,
    upload: Upload,
    metadata: dict,
) -> None:
    df = _load_cleaned_df(upload)
    stats = column_detector.summary(df, metadata)
    plan = dashboard_planner.build_plan(
        df,
        metadata,
        stats,
        user_description=upload.user_description,
    )
    dataset.schema_json = json.dumps(metadata)
    dataset.data_summary = json.dumps(stats)
    dataset.dashboard_plan_json = json.dumps(plan)


@router.patch("/{dataset_id}")
def patch_dataset(
    dataset_id: str,
    body: DatasetPatchBody,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    row = get_dataset_upload_in_workspace(db, dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, upload = row

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    schema_keys = {"primary_date_column", "primary_amount_column", "segment_columns"}
    touch_schema = bool(schema_keys & set(updates.keys()))

    if touch_schema:
        metadata = json.loads(dataset.schema_json or "{}")
        df = _load_cleaned_df(upload)
        actual = set(df.columns)

        if "primary_date_column" in updates:
            col = updates["primary_date_column"]
            if col:
                if col not in actual:
                    raise HTTPException(400, f"Unknown column: {col}")
                metadata["date_columns"] = [col]
            else:
                metadata["date_columns"] = []

        if "primary_amount_column" in updates:
            col = updates["primary_amount_column"]
            if col:
                if col not in actual:
                    raise HTTPException(400, f"Unknown column: {col}")
                metadata["revenue_columns"] = [col]
                nums = [n for n in (metadata.get("numeric_columns") or []) if n != col]
                metadata["numeric_columns"] = nums
            else:
                metadata["revenue_columns"] = []

        if "segment_columns" in updates:
            segs = updates["segment_columns"] or []
            for s in segs:
                if s not in actual:
                    raise HTTPException(400, f"Unknown segment column: {s}")
            metadata["category_columns"] = list(segs)

        _rebuild_after_schema_edit(dataset, upload, metadata)

    if "business_classification" in updates:
        cid = updates["business_classification"]
        if cid is not None:
            if cid not in ALLOWED_CLASSIFICATION_IDS:
                raise HTTPException(400, "Invalid business classification")
            dataset.business_classification = cid

    db.commit()
    db.refresh(dataset)

    return {
        "id": dataset.id,
        "business_classification": dataset.business_classification,
        "business_classification_label": CLASSIFICATIONS.get(
            dataset.business_classification or "", "General dataset"
        ),
        "schema_updated": touch_schema,
    }


@router.get("/{dataset_id}/preview")
def get_preview(
    dataset_id: str,
    n: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    row = get_dataset_upload_in_workspace(db, dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, upload = row

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
def delete_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    row = get_dataset_upload_in_workspace(db, dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, upload = row

    wk = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if wk and wk.outlook_forecast_dataset_id == dataset_id:
        wk.outlook_forecast_dataset_id = None
        wk.outlook_forecast_date_column = None
        wk.outlook_forecast_value_column = None

    db.query(WorkspaceTimelineSnapshot).filter(
        WorkspaceTimelineSnapshot.dataset_id == dataset_id
    ).delete(synchronize_session="fetch")

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


@router.post("/{dataset_id}/append")
async def append_to_dataset(
    dataset_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    check_upload_rate_limit(user.email)
    row = get_dataset_upload_in_workspace(db, dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, upload = row

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported")

    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")

    df_existing = pd.read_parquet(str(parquet_path))

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = upload_dir / f"tmp_append_{dataset_id}{ext}"
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    try:
        ok = await save_upload_stream_limited(file, tmp_path, max_bytes)
        if not ok:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
            )

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
    plan = dashboard_planner.build_plan(
        df_combined,
        metadata,
        stats,
        user_description=upload.user_description,
    )

    df_combined.to_parquet(str(parquet_path), index=False)

    upload.row_count = len(df_combined)
    upload.column_count = len(df_combined.columns)

    dataset.schema_json = json.dumps(metadata)
    dataset.data_summary = json.dumps(stats)
    dataset.cleaned_report_json = json.dumps(clean_report)
    dataset.dashboard_plan_json = json.dumps(plan)

    db.commit()
    db.refresh(dataset)

    try:
        record_append_snapshot(db, workspace_id, dataset, upload)
    except Exception:
        pass

    return {
        "dataset_id": dataset.id,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "cleaning_report": clean_report,
    }
