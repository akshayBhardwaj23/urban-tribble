from __future__ import annotations

import json
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.models import User, Workspace
from services.cleaned_parquet import CleanedDataMissingError, ensure_cleaned_parquet
from services.subscription_usage import assert_workspace_create_allowed
from services.workspace_query import get_dataset_upload_in_workspace
from utils.email_norm import user_by_email_ci

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str


class PatchOutlookForecastRequest(BaseModel):
    """Set all three for a fixed source, or omit / null all three for automatic selection."""

    dataset_id: Optional[str] = None
    date_column: Optional[str] = None
    value_column: Optional[str] = None


def _workspace_outlook_fields(w: Workspace) -> dict:
    return {
        "outlook_forecast_dataset_id": w.outlook_forecast_dataset_id,
        "outlook_forecast_date_column": w.outlook_forecast_date_column,
        "outlook_forecast_value_column": w.outlook_forecast_value_column,
    }


@router.post("/")
def create_workspace(
    req: CreateWorkspaceRequest,
    x_user_email: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_email:
        raise HTTPException(401, "Authentication required")

    user = user_by_email_ci(db, x_user_email)
    if not user:
        raise HTTPException(404, "User not found")

    assert_workspace_create_allowed(db, user)

    workspace = Workspace(name=req.name, owner_id=user.id)
    db.add(workspace)
    db.flush()

    user.active_workspace_id = workspace.id
    db.commit()
    db.refresh(workspace)

    return {
        "id": workspace.id,
        "name": workspace.name,
        "owner_id": workspace.owner_id,
        "created_at": workspace.created_at.isoformat(),
        **_workspace_outlook_fields(workspace),
    }


@router.get("/")
def list_workspaces(
    x_user_email: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_email:
        raise HTTPException(401, "Authentication required")

    user = user_by_email_ci(db, x_user_email)
    if not user:
        raise HTTPException(404, "User not found")

    workspaces = (
        db.query(Workspace).filter(Workspace.owner_id == user.id).all()
    )

    return [
        {
            "id": w.id,
            "name": w.name,
            "is_active": w.id == user.active_workspace_id,
            "created_at": w.created_at.isoformat(),
            **_workspace_outlook_fields(w),
        }
        for w in workspaces
    ]


@router.post("/{workspace_id}/activate")
def activate_workspace(
    workspace_id: str,
    x_user_email: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_email:
        raise HTTPException(401, "Authentication required")

    user = user_by_email_ci(db, x_user_email)
    if not user:
        raise HTTPException(404, "User not found")

    workspace = (
        db.query(Workspace)
        .filter(Workspace.id == workspace_id, Workspace.owner_id == user.id)
        .first()
    )
    if not workspace:
        raise HTTPException(404, "Workspace not found")

    user.active_workspace_id = workspace_id
    db.commit()

    return {"active_workspace_id": workspace_id}


@router.patch("/{workspace_id}/outlook-forecast")
def patch_outlook_forecast(
    workspace_id: str,
    body: PatchOutlookForecastRequest,
    x_user_email: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Save which dataset and columns power the workspace Outlook chart (or clear for auto)."""
    if not x_user_email:
        raise HTTPException(401, "Authentication required")

    user = user_by_email_ci(db, x_user_email)
    if not user:
        raise HTTPException(404, "User not found")

    workspace = (
        db.query(Workspace)
        .filter(Workspace.id == workspace_id, Workspace.owner_id == user.id)
        .first()
    )
    if not workspace:
        raise HTTPException(404, "Workspace not found")

    ds_id = (body.dataset_id or "").strip() or None
    dc = (body.date_column or "").strip() or None
    vc = (body.value_column or "").strip() or None

    has_any = bool(ds_id or dc or vc)
    has_all = bool(ds_id and dc and vc)
    if has_any and not has_all:
        raise HTTPException(
            400,
            "Provide dataset_id, date_column, and value_column together, or omit all three for automatic selection.",
        )

    if not has_all:
        workspace.outlook_forecast_dataset_id = None
        workspace.outlook_forecast_date_column = None
        workspace.outlook_forecast_value_column = None
        db.commit()
        db.refresh(workspace)
        return {"ok": True, **_workspace_outlook_fields(workspace)}

    row = get_dataset_upload_in_workspace(db, ds_id, workspace_id)
    if not row:
        raise HTTPException(400, "Dataset not found in this workspace.")

    dataset, upload = row
    schema = json.loads(dataset.schema_json) if dataset.schema_json else {}
    date_ok = set(schema.get("date_columns") or [])
    value_ok = set(schema.get("revenue_columns") or []) | set(
        schema.get("numeric_columns") or []
    )

    try:
        parquet_path = ensure_cleaned_parquet(upload)
    except CleanedDataMissingError:
        raise HTTPException(400, "Cleaned data file not found for this dataset.")

    df = pd.read_parquet(str(parquet_path))
    if dc not in df.columns or vc not in df.columns:
        raise HTTPException(
            400, "Selected columns are not present in the dataset file.",
        )
    if dc not in date_ok:
        raise HTTPException(
            400, "Date column must be one of the workspace-detected date columns for this file.",
        )
    if vc not in value_ok:
        raise HTTPException(
            400,
            "Value column must be a detected revenue or numeric column for this file.",
        )

    workspace.outlook_forecast_dataset_id = ds_id
    workspace.outlook_forecast_date_column = dc
    workspace.outlook_forecast_value_column = vc
    db.commit()
    db.refresh(workspace)

    return {"ok": True, **_workspace_outlook_fields(workspace)}
