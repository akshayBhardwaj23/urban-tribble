from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.models import User, Workspace

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SyncUserRequest(BaseModel):
    email: str
    name: Optional[str] = None
    image: Optional[str] = None


@router.post("/sync")
def sync_user(req: SyncUserRequest, db: Session = Depends(get_db)):
    """Called by frontend after NextAuth login. Creates user if new."""
    user = db.query(User).filter(User.email == req.email).first()

    if not user:
        user = User(email=req.email, name=req.name, image=req.image)
        db.add(user)
        db.commit()
        db.refresh(user)

    else:
        if req.name and req.name != user.name:
            user.name = req.name
        if req.image and req.image != user.image:
            user.image = req.image
        db.commit()
        db.refresh(user)

    workspaces = (
        db.query(Workspace).filter(Workspace.owner_id == user.id).all()
    )

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        "active_workspace_id": user.active_workspace_id,
        "needs_onboarding": len(workspaces) == 0,
        "workspaces": [
            {"id": w.id, "name": w.name, "created_at": w.created_at.isoformat()}
            for w in workspaces
        ],
    }


@router.get("/me")
def get_me(
    x_user_email: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Get current user profile + workspaces."""
    if not x_user_email:
        raise HTTPException(401, "Not authenticated")

    user = db.query(User).filter(User.email == x_user_email).first()
    if not user:
        raise HTTPException(404, "User not found")

    workspaces = (
        db.query(Workspace).filter(Workspace.owner_id == user.id).all()
    )

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        "active_workspace_id": user.active_workspace_id,
        "workspaces": [
            {"id": w.id, "name": w.name, "created_at": w.created_at.isoformat()}
            for w in workspaces
        ],
    }
