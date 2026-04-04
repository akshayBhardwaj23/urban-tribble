"""Normalize email for lookups and storage (single account per mailbox)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.models import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_by_email_ci(db: Session, email: str) -> User | None:
    """Case-insensitive match so Google vs typed email stay one user."""
    n = normalize_email(email)
    return (
        db.query(User).filter(func.lower(User.email) == n).first()
    )
