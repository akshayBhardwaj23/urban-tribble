"""Query helpers scoped to a single workspace (via Upload.workspace_id)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models.models import Analysis, Dataset, Upload


def dataset_upload_pairs_for_workspace(db: Session, workspace_id: str):
    """Ordered query of (Dataset, Upload) for the active workspace."""
    return (
        db.query(Dataset, Upload)
        .join(Upload, Dataset.upload_id == Upload.id)
        .filter(Upload.workspace_id == workspace_id)
        .order_by(Dataset.created_at.desc())
    )


def get_dataset_upload_in_workspace(
    db: Session, dataset_id: str, workspace_id: str
) -> Optional[tuple[Dataset, Upload]]:
    row = (
        db.query(Dataset, Upload)
        .join(Upload, Dataset.upload_id == Upload.id)
        .filter(Dataset.id == dataset_id, Upload.workspace_id == workspace_id)
        .first()
    )
    return row


def latest_workspace_overview_analysis(
    db: Session, workspace_id: str
) -> Optional[Analysis]:
    """Most recent workspace-level analysis tied to a dataset in this workspace."""
    return (
        db.query(Analysis)
        .join(Dataset, Analysis.dataset_id == Dataset.id)
        .join(Upload, Dataset.upload_id == Upload.id)
        .filter(
            Analysis.type == "workspace_overview",
            Upload.workspace_id == workspace_id,
        )
        .order_by(Analysis.created_at.desc())
        .first()
    )
