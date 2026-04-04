from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.models import User, Workspace
from utils.email_norm import user_by_email_ci

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str


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
