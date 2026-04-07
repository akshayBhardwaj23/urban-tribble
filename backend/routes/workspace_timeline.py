from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps import require_active_workspace
from models.models import User, WorkspaceTimelineSnapshot
from services.subscription_usage import assert_timeline_allowed
from services.workspace_timeline import (
    compare_snapshots,
    list_recent_digests,
    list_snapshots,
    serialize_snapshot,
    compute_evolution,
)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


def _get_snapshot_row(
    db: Session, workspace_id: str, snapshot_id: str
) -> WorkspaceTimelineSnapshot:
    row = (
        db.query(WorkspaceTimelineSnapshot)
        .filter(
            WorkspaceTimelineSnapshot.id == snapshot_id,
            WorkspaceTimelineSnapshot.workspace_id == workspace_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Snapshot not found")
    return row


@router.get("/timeline")
def get_workspace_timeline(
    limit: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    assert_timeline_allowed(db, user)
    rows = list_snapshots(db, workspace_id, limit)
    events_desc = [serialize_snapshot(r) for r in rows]
    chrono_asc = list(reversed(events_desc))
    return {
        "events": events_desc,
        "evolution": compute_evolution(chrono_asc),
        "digests": list_recent_digests(db, workspace_id, limit=8),
    }


@router.get("/timeline/compare")
def compare_workspace_snapshots(
    from_snapshot_id: str = Query(..., alias="from"),
    to_snapshot_id: str = Query(..., alias="to"),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    assert_timeline_allowed(db, user)
    if from_snapshot_id == to_snapshot_id:
        raise HTTPException(400, "Choose two different snapshots")
    ra = _get_snapshot_row(db, workspace_id, from_snapshot_id)
    rb = _get_snapshot_row(db, workspace_id, to_snapshot_id)
    sa = serialize_snapshot(ra)
    sb = serialize_snapshot(rb)
    if sa["created_at"] and sb["created_at"] and sa["created_at"] > sb["created_at"]:
        sa, sb = sb, sa
    return compare_snapshots(sa, sb)
