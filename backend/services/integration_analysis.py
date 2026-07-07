"""Auto-run analysis after a successful integration sync."""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from models.models import Analysis, Dataset, Upload, User
from services.ai_analyzer import AIAnalyzer
from services.subscription_usage import (
    assert_analysis_allowed,
    get_effective_plan,
    trim_free_analysis_result,
)
from services.workspace_query import get_dataset_upload_in_workspace

_ai_analyzer = AIAnalyzer()


def run_post_sync_analysis(
    db: Session,
    workspace_id: str,
    dataset: Dataset,
) -> Optional[str]:
    """Run overview analysis if plan allows; returns analysis id or None."""
    row = get_dataset_upload_in_workspace(db, dataset.id, workspace_id)
    if not row:
        return None
    dataset, upload = row

    from models.models import Workspace

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return None
    user = db.query(User).filter(User.id == ws.owner_id).first()
    if not user:
        return None

    try:
        assert_analysis_allowed(db, user, workspace_id)
    except Exception:
        return None

    data_summary = json.loads(dataset.data_summary) if dataset.data_summary else {}
    column_metadata = json.loads(dataset.schema_json) if dataset.schema_json else {}
    user_description = upload.user_description if upload else None

    result = _ai_analyzer.analyze(data_summary, column_metadata, user_description)
    if get_effective_plan(db, user) == "free":
        result = trim_free_analysis_result(result)

    analysis = Analysis(
        dataset_id=dataset.id,
        type="overview",
        result_json=json.dumps(result),
        ai_summary=result.get("executive_summary", ""),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis.id
