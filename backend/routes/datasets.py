import json
from pathlib import Path
from typing import Dict, List, Optional

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
    DataSourceIntegration,
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
from services import overview_cache
from services.ingestion_classifier import ALLOWED_CLASSIFICATION_IDS, CLASSIFICATIONS
from services.dashboard_stability import parse_metadata_json, should_rebuild_dashboard_plan
from services.column_detector import ColumnDetector
from services.dashboard_planner import DashboardPlanner
from services.data_cleaner import DataCleaner
from services.file_processor import FileProcessor
from services.file_validation import (
    FileValidationError,
    validate_frame_size,
    validate_magic_bytes,
)
from services import storage
from services.subscription_usage import assert_upload_allowed
from services.upload_io import save_upload_stream_limited
from services.upload_rate_limit import check_upload_rate_limit
from services.cleaned_parquet import CleanedDataMissingError, ensure_cleaned_parquet
from services.workspace_timeline import record_append_snapshot

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

dashboard_planner = DashboardPlanner()
column_detector = ColumnDetector()


class DatasetPatchBody(BaseModel):
    business_classification: Optional[str] = None
    primary_date_column: Optional[str] = None
    primary_amount_column: Optional[str] = None
    segment_columns: Optional[List[str]] = None
    dayfirst: Optional[bool] = None
    drop_duplicates: Optional[bool] = None
    sheet: Optional[str] = None
    header_row: Optional[int] = None
    column_roles: Optional[Dict[str, str]] = None  # {column_name: role}


def _load_cleaned_df(upload: Upload) -> pd.DataFrame:
    try:
        parquet_path = ensure_cleaned_parquet(upload)
    except CleanedDataMissingError:
        raise HTTPException(404, "Cleaned data file not found")
    return pd.read_parquet(str(parquet_path))


@router.get("/")
def list_datasets(
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    datasets = dataset_upload_pairs_for_workspace(db, workspace_id).all()
    integration_ids = [ds.integration_id for ds, _ in datasets if ds.integration_id]
    integrations_by_id: dict[str, DataSourceIntegration] = {}
    if integration_ids:
        for row in (
            db.query(DataSourceIntegration)
            .filter(DataSourceIntegration.id.in_(integration_ids))
            .all()
        ):
            integrations_by_id[row.id] = row
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
            "integration_id": ds.integration_id,
            "dashboard_plan_locked": bool(ds.dashboard_plan_locked),
            "integration": (
                {
                    "id": integ.id,
                    "provider": integ.provider,
                    "name": integ.name,
                    "status": integ.status.value,
                    "refresh_interval_hours": integ.refresh_interval_hours,
                    "last_sync_at": integ.last_sync_at.isoformat() if integ.last_sync_at else None,
                    "next_sync_at": integ.next_sync_at.isoformat() if integ.next_sync_at else None,
                }
                if ds.integration_id and (integ := integrations_by_id.get(ds.integration_id))
                else None
            ),
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
    dataset, upload = row

    integration_payload = None
    if dataset.integration_id:
        integ = (
            db.query(DataSourceIntegration)
            .filter(
                DataSourceIntegration.id == dataset.integration_id,
                DataSourceIntegration.workspace_id == workspace_id,
            )
            .first()
        )
        if integ:
            integration_payload = {
                "id": integ.id,
                "provider": integ.provider,
                "name": integ.name,
                "status": integ.status.value,
                "refresh_interval_hours": integ.refresh_interval_hours,
                "last_sync_at": integ.last_sync_at.isoformat() if integ.last_sync_at else None,
                "next_sync_at": integ.next_sync_at.isoformat() if integ.next_sync_at else None,
                "auto_analyze": bool(integ.auto_analyze),
            }

    sheets: list = []
    try:
        from services import storage as object_storage

        if upload.file_url and upload.file_type in (".xlsx", ".xls"):
            local = object_storage.materialize(upload.file_url)
            if Path(local).exists():
                sheets = FileProcessor().list_sheets(str(local))
    except Exception:
        sheets = []

    return {
        "id": dataset.id,
        "upload_id": dataset.upload_id,
        "name": dataset.name,
        "schema_json": json.loads(dataset.schema_json) if dataset.schema_json else None,
        "data_summary": json.loads(dataset.data_summary) if dataset.data_summary else None,
        "cleaned_report": json.loads(dataset.cleaned_report_json) if dataset.cleaned_report_json else None,
        "mapping_spec": json.loads(dataset.mapping_spec_json) if dataset.mapping_spec_json else None,
        "sheets": sheets,
        "business_classification": dataset.business_classification,
        "created_at": dataset.created_at.isoformat(),
        "integration_id": dataset.integration_id,
        "dashboard_plan_locked": bool(dataset.dashboard_plan_locked),
        "integration": integration_payload,
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

    # Keep MappingSpec in sync with user overrides
    spec = {}
    if dataset.mapping_spec_json:
        try:
            spec = json.loads(dataset.mapping_spec_json)
        except (json.JSONDecodeError, TypeError):
            spec = {}
    if not spec:
        from services.column_profile import build_mapping_spec

        spec = build_mapping_spec(df, metadata, source="user")
    else:
        spec["source"] = "user"
        spec["primary_timeline"] = (metadata.get("date_columns") or [None])[0]
        spec["primary_amount"] = (metadata.get("revenue_columns") or [None])[0]
        role_by_name = {c["name"]: c for c in (spec.get("columns") or [])}
        for col in metadata.get("date_columns") or []:
            if col in role_by_name:
                role_by_name[col]["role"] = "timeline"
        for col in metadata.get("revenue_columns") or []:
            if col in role_by_name:
                role_by_name[col]["role"] = "amount_inflow"
        for col in metadata.get("category_columns") or []:
            if col in role_by_name:
                role_by_name[col]["role"] = "dimension"
        if "ingestion_profile" in spec and isinstance(spec["ingestion_profile"], dict):
            spec["ingestion_profile"]["column_highlights"] = {
                "date_columns": list(metadata.get("date_columns") or []),
                "revenue_columns": list(metadata.get("revenue_columns") or []),
                "expense_columns": list(metadata.get("expense_columns") or []),
                "category_columns": list(metadata.get("category_columns") or []),
                "numeric_columns": list(metadata.get("numeric_columns") or []),
                "text_columns": list(metadata.get("text_columns") or []),
            }
    dataset.mapping_spec_json = json.dumps(spec)


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

    schema_keys = {
        "primary_date_column",
        "primary_amount_column",
        "segment_columns",
        "dayfirst",
        "drop_duplicates",
        "sheet",
        "header_row",
        "column_roles",
    }
    touch_schema = bool(schema_keys & set(updates.keys()))
    needs_rebuild_from_source = bool(
        {"dayfirst", "drop_duplicates", "sheet", "header_row", "column_roles"}
        & set(updates.keys())
    )

    if touch_schema:
        metadata = json.loads(dataset.schema_json or "{}")
        # Load mapping spec early
        spec: dict = {}
        if dataset.mapping_spec_json:
            try:
                spec = json.loads(dataset.mapping_spec_json)
            except (json.JSONDecodeError, TypeError):
                spec = {}

        if needs_rebuild_from_source:
            from services.cleaned_parquet import rebuild_from_sources
            from services.column_profile import (
                VALID_ROLES,
                metadata_from_mapping_spec,
            )

            if "dayfirst" in updates:
                spec["dayfirst"] = updates["dayfirst"]
            if "drop_duplicates" in updates:
                spec["drop_duplicates"] = bool(updates["drop_duplicates"])
            if "sheet" in updates:
                spec["sheet"] = updates["sheet"]
            if "header_row" in updates and updates["header_row"] is not None:
                spec["header_row"] = int(updates["header_row"])
            if "column_roles" in updates and updates["column_roles"]:
                roles = updates["column_roles"]
                by_name = {c["name"]: c for c in (spec.get("columns") or [])}
                for name, role in roles.items():
                    if role not in VALID_ROLES:
                        raise HTTPException(400, f"Invalid role: {role}")
                    if name in by_name:
                        by_name[name]["role"] = role
            spec["source"] = "user"
            dataset.mapping_spec_json = json.dumps(spec)

            df, clean_report = rebuild_from_sources(upload, dataset=dataset)
            metadata = metadata_from_mapping_spec(spec)
            # Apply primary overrides after role remap
            if "primary_date_column" in updates:
                col = updates["primary_date_column"]
                metadata["primary_timeline"] = col
                metadata["date_columns"] = [col] if col else []
                spec["primary_timeline"] = col
            if "primary_amount_column" in updates:
                col = updates["primary_amount_column"]
                metadata["primary_amount"] = col
                if col:
                    metadata["revenue_columns"] = [col] + [
                        c for c in (metadata.get("revenue_columns") or []) if c != col
                    ]
                spec["primary_amount"] = col
            if "segment_columns" in updates:
                metadata["category_columns"] = list(updates["segment_columns"] or [])

            dataset.mapping_spec_json = json.dumps(spec)
            dataset.cleaned_report_json = json.dumps(clean_report)
            _rebuild_after_schema_edit(dataset, upload, metadata)
        else:
            df = _load_cleaned_df(upload)
            actual = set(df.columns)

            if "primary_date_column" in updates:
                col = updates["primary_date_column"]
                if col:
                    if col not in actual:
                        raise HTTPException(400, f"Unknown column: {col}")
                    metadata["date_columns"] = [col]
                    metadata["primary_timeline"] = col
                else:
                    metadata["date_columns"] = []
                    metadata["primary_timeline"] = None

            if "primary_amount_column" in updates:
                col = updates["primary_amount_column"]
                if col:
                    if col not in actual:
                        raise HTTPException(400, f"Unknown column: {col}")
                    metadata["revenue_columns"] = [col]
                    metadata["primary_amount"] = col
                    nums = [n for n in (metadata.get("numeric_columns") or []) if n != col]
                    metadata["numeric_columns"] = nums
                else:
                    metadata["revenue_columns"] = []
                    metadata["primary_amount"] = None

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
    overview_cache.invalidate(workspace_id)

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
        from services.cleaned_parquet import invalidate_cleaned_parquet
        from services.source_files import delete_all_sources

        delete_all_sources(upload)
        invalidate_cleaned_parquet(upload)
        db.delete(upload)

    db.commit()
    overview_cache.invalidate(workspace_id)
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
    check_upload_rate_limit(db, user.email)
    assert_upload_allowed(db, user, workspace_id)
    row = get_dataset_upload_in_workspace(db, dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, upload = row

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported")

    # Persist the append as a durable source file; it is never discarded.
    from uuid import uuid4

    append_id = str(uuid4())[:8]
    append_key = storage.upload_key(upload.id, f"_append_{append_id}{ext}")
    staging = Path(settings.UPLOAD_DIR) / ".incoming" / f"{upload.id}_append_{append_id}{ext}"
    staging.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    ok = await save_upload_stream_limited(file, staging, max_bytes)
    if not ok:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
        )

    try:
        validate_magic_bytes(staging, ext)
        df_new = file_processor.read(str(staging))
        validate_frame_size(df_new, filename=file.filename)
    except FileValidationError as e:
        staging.unlink(missing_ok=True)
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        staging.unlink(missing_ok=True)
        raise HTTPException(422, f"Failed to read append file: {e}") from e

    from services.cleaned_parquet import rebuild_from_sources
    from services.source_files import append_source_file

    # Compatibility check against current cleaned columns
    try:
        parquet_path = ensure_cleaned_parquet(upload)
        df_existing = pd.read_parquet(str(parquet_path))
    except CleanedDataMissingError:
        staging.unlink(missing_ok=True)
        raise HTTPException(404, "Cleaned data file not found")

    existing_cols = set(c.lower() for c in df_existing.columns)
    # Normalize new columns the same way cleaner would for overlap check
    new_cols_raw = set(str(c).lower() for c in df_new.columns)
    overlap = existing_cols & new_cols_raw
    # Also try normalized names
    import re

    def _norm(c: str) -> str:
        n = re.sub(r"\s+", "_", str(c).strip()).lower()
        return re.sub(r"[^\w]", "", n)

    new_norm = {_norm(c) for c in df_new.columns}
    overlap_norm = existing_cols & new_norm
    best_overlap = max(len(overlap), len(overlap_norm))

    # Require near-exact overlap so append cannot silently misalign schemas.
    # Allow at most one missing/extra column on small files; otherwise ≥90%.
    min_needed = max(1, int(len(existing_cols) * 0.9)) if len(existing_cols) > 4 else len(existing_cols)
    if best_overlap < min_needed:
        staging.unlink(missing_ok=True)
        raise HTTPException(
            400,
            f"Column mismatch: new file shares only {best_overlap} of "
            f"{len(existing_cols)} columns. Align headers before appending.",
        )

    storage.upload_file(staging, append_key)
    append_source_file(
        upload,
        key=append_key,
        filename=file.filename or f"append{ext}",
        kind="append",
    )

    # Re-derive from ALL raw sources (original + appends) — never re-clean parquet
    df_combined, clean_report = rebuild_from_sources(upload, dataset=dataset)

    # Re-profile without re-cleaning (already cleaned by rebuild)
    metadata = column_detector.detect(df_combined)
    metadata["all_columns"] = [str(c) for c in df_combined.columns]
    stats = column_detector.summary(df_combined, metadata)
    old_metadata = parse_metadata_json(dataset.schema_json)
    rebuild_plan = should_rebuild_dashboard_plan(
        dashboard_plan_locked=bool(dataset.dashboard_plan_locked),
        old_metadata=old_metadata,
        new_metadata=metadata,
        existing_plan_json=dataset.dashboard_plan_json,
    )
    if rebuild_plan:
        plan = dashboard_planner.build_plan(
            df_combined,
            metadata,
            stats,
            user_description=upload.user_description,
        )
        dataset.dashboard_plan_json = json.dumps(plan)

    upload.row_count = len(df_combined)
    upload.column_count = len(df_combined.columns)

    dataset.schema_json = json.dumps(metadata)
    dataset.data_summary = json.dumps(stats)
    dataset.cleaned_report_json = json.dumps(clean_report)

    # Refresh profiles but preserve the user's mapping policy and roles.
    if dataset.mapping_spec_json:
        try:
            from services.column_profile import (
                build_mapping_spec,
                metadata_from_mapping_spec,
            )

            old_spec = json.loads(dataset.mapping_spec_json)
            old_roles = {
                str(c.get("name")): str(c.get("role") or "text")
                for c in (old_spec.get("columns") or [])
                if c.get("name")
            }
            # Prefer prior roles when rebuilding metadata lists for known columns.
            for col_name, role in old_roles.items():
                if col_name not in df_combined.columns:
                    continue
                # Clear from auto lists then re-apply via roles_from later
                for key in (
                    "date_columns",
                    "revenue_columns",
                    "expense_columns",
                    "category_columns",
                    "numeric_columns",
                    "text_columns",
                ):
                    if col_name in (metadata.get(key) or []):
                        metadata[key] = [c for c in metadata[key] if c != col_name]
                if role == "timeline":
                    metadata.setdefault("date_columns", []).insert(0, col_name)
                elif role == "amount_inflow":
                    metadata.setdefault("revenue_columns", []).insert(0, col_name)
                elif role == "amount_outflow":
                    metadata.setdefault("expense_columns", []).insert(0, col_name)
                elif role == "dimension":
                    metadata.setdefault("category_columns", []).append(col_name)
                elif role in ("quantity", "identifier"):
                    metadata.setdefault("numeric_columns", []).append(col_name)
                elif role != "ignore":
                    metadata.setdefault("text_columns", []).append(col_name)

            spec = build_mapping_spec(
                df_combined,
                metadata,
                clean_report=clean_report,
                source=old_spec.get("source") or "auto",
                sheet=old_spec.get("sheet"),
                header_row=int(old_spec.get("header_row") or 0),
                drop_duplicates=bool(old_spec.get("drop_duplicates")),
                dayfirst=old_spec.get("dayfirst"),
                primary_timeline=old_spec.get("primary_timeline"),
                primary_amount=old_spec.get("primary_amount"),
                ingestion_profile=old_spec.get("ingestion_profile"),
            )
            # Restore per-column roles / meanings / date_format for columns that still exist
            old_by_name = {
                str(c.get("name")): c for c in (old_spec.get("columns") or []) if c.get("name")
            }
            for col in spec.get("columns") or []:
                prev = old_by_name.get(col.get("name") or "")
                if not prev:
                    continue
                if prev.get("role"):
                    col["role"] = prev["role"]
                if prev.get("meaning"):
                    col["meaning"] = prev["meaning"]
                if prev.get("date_format"):
                    col["date_format"] = prev["date_format"]
                if prev.get("original_name"):
                    col["original_name"] = prev["original_name"]
            # Keep schema_json aligned with preserved roles
            dataset.schema_json = json.dumps(metadata_from_mapping_spec(spec))
            dataset.mapping_spec_json = json.dumps(spec)
        except Exception:
            pass

    db.commit()
    db.refresh(dataset)
    overview_cache.invalidate(workspace_id)

    try:
        record_append_snapshot(db, workspace_id, dataset, upload)
    except Exception:
        pass

    return {
        "dataset_id": dataset.id,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "cleaning_report": clean_report,
        "source_files": parse_source_files(upload),
    }
