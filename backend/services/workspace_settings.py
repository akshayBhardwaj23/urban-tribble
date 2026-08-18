"""Per-workspace display preferences."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.models import Workspace
from services.currency import normalize_currency


def currency_for_workspace(db: Session, workspace_id: str | None) -> str:
    """Currency code for a workspace, falling back to DEFAULT_CURRENCY."""
    if not workspace_id:
        return normalize_currency(None)
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    return normalize_currency(getattr(workspace, "currency", None) if workspace else None)
