"""Auto-run analysis after a successful integration sync."""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.models import Analysis, Dataset
from services.ai_analyzer import AIAnalyzer
from services.subscription_usage import (
    assert_analysis_allowed,
    get_effective_plan,
    trim_free_analysis_result,
)
from services.workspace_query import get_dataset_upload_in_workspace, workspace_owner
from services.workspace_settings import currency_for_workspace

_ai_analyzer = AIAnalyzer()


def _plan_limit_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict) and detail.get("message"):
        return str(detail["message"])
    return str(exc) or "Analysis limit reached for your plan."


def run_post_sync_analysis(
    db: Session,
    workspace_id: str,
    dataset: Dataset,
) -> tuple[str | None, str | None]:
    """Run overview analysis if plan allows.

    Returns ``(analysis_id, skipped_reason)`` -- exactly one is set. A plan
    limit is a real, user-facing outcome ("synced, but no new briefing because
    you're at your analysis cap"), not an internal error, so it is returned
    rather than swallowed silently.
    """
    row = get_dataset_upload_in_workspace(db, dataset.id, workspace_id)
    if not row:
        return None, "Dataset not found for analysis."
    dataset, upload = row

    user = workspace_owner(db, workspace_id)
    if not user:
        return None, "Workspace owner not found."

    try:
        assert_analysis_allowed(db, user, workspace_id)
    except HTTPException as e:
        return None, _plan_limit_message(e)

    data_summary = json.loads(dataset.data_summary) if dataset.data_summary else {}
    column_metadata = json.loads(dataset.schema_json) if dataset.schema_json else {}
    user_description = upload.user_description if upload else None

    result = _ai_analyzer.analyze(
        data_summary,
        column_metadata,
        user_description,
        currency=currency_for_workspace(db, getattr(upload, "workspace_id", None)),
    )
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
    return analysis.id, None
