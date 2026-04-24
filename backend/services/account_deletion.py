"""Cascade-delete a user’s workspaces (files + DB rows) and the user record."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from models.models import (
    Analysis,
    ChatMessage,
    Dashboard,
    Dataset,
    DatasetRelation,
    LoginOtpChallenge,
    Upload,
    User,
    Workspace,
    WorkspaceRecurringSummary,
    WorkspaceTimelineSnapshot,
)
from services.workspace_query import dataset_upload_pairs_for_workspace
from utils.email_norm import normalize_email


def _unlink_upload_files(upload: Upload) -> None:
    original = Path(upload.file_url)
    if original.exists():
        original.unlink()
    parquet = original.parent / f"{upload.id}_cleaned.parquet"
    if parquet.exists():
        parquet.unlink()


def _delete_dataset_pair(db: Session, workspace_id: str, dataset: Dataset, upload: Upload) -> None:
    wk = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if wk and wk.outlook_forecast_dataset_id == dataset.id:
        wk.outlook_forecast_dataset_id = None
        wk.outlook_forecast_date_column = None
        wk.outlook_forecast_value_column = None

    db.query(WorkspaceTimelineSnapshot).filter(
        WorkspaceTimelineSnapshot.dataset_id == dataset.id
    ).delete(synchronize_session="fetch")

    db.query(ChatMessage).filter(ChatMessage.dataset_id == dataset.id).delete()
    db.query(Analysis).filter(Analysis.dataset_id == dataset.id).delete()
    db.query(DatasetRelation).filter(
        (DatasetRelation.source_dataset_id == dataset.id)
        | (DatasetRelation.target_dataset_id == dataset.id)
    ).delete(synchronize_session="fetch")

    db.delete(dataset)
    _unlink_upload_files(upload)
    db.delete(upload)


def delete_workspace_cascade(db: Session, workspace: Workspace) -> None:
    pairs = dataset_upload_pairs_for_workspace(db, workspace.id).all()
    for dataset, upload in pairs:
        _delete_dataset_pair(db, workspace.id, dataset, upload)

    db.query(WorkspaceTimelineSnapshot).filter(
        WorkspaceTimelineSnapshot.workspace_id == workspace.id
    ).delete(synchronize_session="fetch")
    db.query(WorkspaceRecurringSummary).filter(
        WorkspaceRecurringSummary.workspace_id == workspace.id
    ).delete(synchronize_session="fetch")
    db.query(DatasetRelation).filter(DatasetRelation.workspace_id == workspace.id).delete(
        synchronize_session="fetch"
    )
    db.query(Dashboard).filter(Dashboard.workspace_id == workspace.id).delete(
        synchronize_session="fetch"
    )
    db.delete(workspace)


def delete_user_account(db: Session, user: User) -> None:
    """Remove all owned workspaces (including files on disk) and the user."""
    workspaces = db.query(Workspace).filter(Workspace.owner_id == user.id).all()
    for w in workspaces:
        delete_workspace_cascade(db, w)

    email_norm = normalize_email(user.email)
    db.query(LoginOtpChallenge).filter(LoginOtpChallenge.email == email_norm).delete(
        synchronize_session="fetch"
    )

    db.delete(user)
    db.commit()
