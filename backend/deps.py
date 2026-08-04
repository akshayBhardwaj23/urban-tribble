from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import User, Workspace
from services.api_tokens import TokenError, bearer_from_authorization, verify_access_token


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Resolve the current user from a signed Bearer access token.

    Returns None when no Authorization header is present so endpoints can
    opt into optional auth. Spoofable ``X-User-Email`` is intentionally ignored.
    """
    token = bearer_from_authorization(authorization)
    if not token:
        return None

    try:
        payload = verify_access_token(token)
    except TokenError:
        raise HTTPException(401, "Invalid or expired access token")

    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(401, "Invalid or expired access token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(401, "Invalid or expired access token")
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
