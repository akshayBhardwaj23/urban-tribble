from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import User, Workspace


def get_current_user(
    x_user_email: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Extract current user from X-User-Email header.

    Returns None if no header is present (allows unauthenticated access
    to endpoints that handle it themselves).
    """
    if not x_user_email:
        return None

    user = db.query(User).filter(User.email == x_user_email).first()
    return user


def require_user(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Require authenticated user. Raises 401 if not logged in."""
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def require_active_workspace(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> tuple[User, str]:
    """Require user with a valid active workspace they own. Returns (user, workspace_id)."""
    wid = user.active_workspace_id
    if not wid:
        raise HTTPException(
            400,
            "Select or create a workspace before using this feature.",
        )
    ws = (
        db.query(Workspace)
        .filter(Workspace.id == wid, Workspace.owner_id == user.id)
        .first()
    )
    if not ws:
        raise HTTPException(400, "Active workspace is not valid for this account.")
    return user, wid
