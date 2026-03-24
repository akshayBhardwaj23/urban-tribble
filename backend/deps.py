from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import User


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
