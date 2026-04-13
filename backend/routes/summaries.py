from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from deps import require_active_workspace
from models.models import User
from services.subscription_usage import assert_summary_allowed, get_effective_plan, plan_features
from services.recurring_summary import (
    ensure_summary_for_period,
    list_summary_history,
    latest_stored_summary,
    serialize_summary_row,
)

router = APIRouter(prefix="/api/summaries", tags=["summaries"])


class GenerateSummaryRequest(BaseModel):
    kind: str = Field(..., description="weekly or monthly")
    force: bool = False


@router.get("/latest")
def get_latest_summaries(
    ensure: bool = Query(
        True,
        description="Create summaries for the current canonical period when missing.",
    ),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    plan = get_effective_plan(db, user)
    feats = plan_features(plan)
    weekly = None
    monthly = None
    if ensure:
        if feats["weekly_summary"]:
            weekly = ensure_summary_for_period(db, workspace_id, "weekly")
        if feats["monthly_summary"]:
            monthly = ensure_summary_for_period(db, workspace_id, "monthly")
    else:
        if feats["weekly_summary"]:
            weekly = latest_stored_summary(db, workspace_id, "weekly")
        if feats["monthly_summary"]:
            monthly = latest_stored_summary(db, workspace_id, "monthly")
    return {
        "weekly": serialize_summary_row(weekly) if weekly else None,
        "monthly": serialize_summary_row(monthly) if monthly else None,
    }


@router.get("/history")
def get_summary_history(
    kind: str = Query("weekly", description="weekly or monthly"),
    limit: int = Query(12, ge=1, le=52),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    if kind not in ("weekly", "monthly"):
        raise HTTPException(400, "kind must be weekly or monthly")
    user, workspace_id = ws
    assert_summary_allowed(db, user, kind)
    rows = list_summary_history(db, workspace_id, kind, limit)
    return {"kind": kind, "items": [serialize_summary_row(r) for r in rows]}


@router.post("/generate")
def generate_summary(
    body: GenerateSummaryRequest,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    if body.kind not in ("weekly", "monthly"):
        raise HTTPException(400, "kind must be weekly or monthly")
    user, workspace_id = ws
    assert_summary_allowed(db, user, body.kind)
    row = ensure_summary_for_period(
        db,
        workspace_id,
        body.kind,
        force_refresh=body.force,
    )
    if not row:
        raise HTTPException(
            400,
            "No datasets in this workspace—import data before generating a summary.",
        )
    return serialize_summary_row(row)
