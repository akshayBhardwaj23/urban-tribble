"""Shared ingest path for uploads and integration syncs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from config import settings
from models.models import Dataset, Upload, UploadStatus
from services.column_detector import ColumnDetector
from services.dashboard_planner import DashboardPlanner
from services.dashboard_stability import parse_metadata_json, should_rebuild_dashboard_plan
from services.data_cleaner import DataCleaner
from services.ingestion_classifier import build_ingestion_profile

column_detector = ColumnDetector()
data_cleaner = DataCleaner()
dashboard_planner = DashboardPlanner()


def ingest_dataframe(
    db: Session,
    *,
    df: pd.DataFrame,
    workspace_id: str,
    name: str,
    description: Optional[str] = None,
    upload: Optional[Upload] = None,
    dataset: Optional[Dataset] = None,
    dashboard_plan_locked: bool = False,
) -> Tuple[Upload, Dataset, dict]:
    """Clean, profile, and persist a dataframe as upload + dataset."""
    df, clean_report = data_cleaner.clean(df)
    metadata = column_detector.detect(df)
    metadata["all_columns"] = [str(c) for c in df.columns]
    stats = column_detector.summary(df, metadata)

    old_metadata = parse_metadata_json(dataset.schema_json if dataset else None)
    existing_plan = dataset.dashboard_plan_json if dataset else None
    rebuild_plan = should_rebuild_dashboard_plan(
        dashboard_plan_locked=dashboard_plan_locked,
        old_metadata=old_metadata,
        new_metadata=metadata,
        existing_plan_json=existing_plan,
    )
    if rebuild_plan:
        plan = dashboard_planner.build_plan(
            df,
            metadata,
            stats,
            user_description=description,
        )
        plan_json = json.dumps(plan)
    else:
        plan_json = existing_plan or json.dumps(
            dashboard_planner.build_plan(df, metadata, stats, user_description=description)
        )

    ingestion = build_ingestion_profile(
        name,
        description,
        metadata,
        clean_report,
        list(df.columns),
    )
    cls_id = ingestion["classification"]["id"]

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    if upload is None:
        upload = Upload(
            filename=name,
            file_type=".csv",
            file_url="",
            user_description=description,
            status=UploadStatus.processing,
            workspace_id=workspace_id,
        )
        db.add(upload)
        db.flush()

    file_path = upload_dir / f"{upload.id}.csv"
    df.to_csv(str(file_path), index=False)
    upload.file_url = str(file_path)
    upload.row_count = len(df)
    upload.column_count = len(df.columns)
    upload.status = UploadStatus.completed
    upload.filename = name
    if description is not None:
        upload.user_description = description

    cleaned_path = upload_dir / f"{upload.id}_cleaned.parquet"
    df.to_parquet(str(cleaned_path), index=False)

    if dataset is None:
        dataset = Dataset(
            upload_id=upload.id,
            name=name,
            schema_json=json.dumps(metadata),
            data_summary=json.dumps(stats),
            cleaned_report_json=json.dumps(clean_report),
            dashboard_plan_json=plan_json,
            dashboard_plan_locked=1 if dashboard_plan_locked else 0,
            business_classification=cls_id,
        )
        db.add(dataset)
    else:
        dataset.name = name
        dataset.schema_json = json.dumps(metadata)
        dataset.data_summary = json.dumps(stats)
        dataset.cleaned_report_json = json.dumps(clean_report)
        if rebuild_plan:
            dataset.dashboard_plan_json = plan_json
        dataset.dashboard_plan_locked = 1 if dashboard_plan_locked else dataset.dashboard_plan_locked
        if not dataset.business_classification:
            dataset.business_classification = cls_id

    db.flush()
    return upload, dataset, ingestion
