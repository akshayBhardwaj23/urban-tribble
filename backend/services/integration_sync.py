"""Run integration sync, preserve dashboard layout, and trigger analysis."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from config import settings
from models.models import (
    DataSourceIntegration,
    Dataset,
    IntegrationStatus,
    Upload,
)
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
    fetch_provider_data,
)
from services.integration_registry import get_provider
from services.ingest_pipeline import ingest_dataframe
from services.workspace_query import get_dataset_upload_in_workspace
from services.workspace_timeline import record_append_snapshot, record_upload_snapshot


def _clamp_refresh_hours(hours: int) -> int:
    return max(
        settings.INTEGRATION_MIN_REFRESH_HOURS,
        min(hours, settings.INTEGRATION_MAX_REFRESH_HOURS),
    )


def compute_next_sync_at(refresh_hours: int, from_time: Optional[datetime] = None) -> datetime:
    base = from_time or datetime.utcnow()
    return base + timedelta(hours=_clamp_refresh_hours(refresh_hours))


def integration_to_dict(
    integration: DataSourceIntegration,
    *,
    provider_name: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": integration.id,
        "workspace_id": integration.workspace_id,
        "provider": integration.provider,
        "provider_name": provider_name or integration.provider,
        "name": integration.name,
        "connection_mode": integration.connection_mode,
        "dataset_id": integration.dataset_id,
        "refresh_interval_hours": integration.refresh_interval_hours,
        "auto_analyze": bool(integration.auto_analyze),
        "dashboard_plan_locked": bool(integration.dashboard_plan_locked),
        "status": integration.status.value,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
        "next_sync_at": integration.next_sync_at.isoformat() if integration.next_sync_at else None,
        "last_sync_error": integration.last_sync_error,
        "created_at": integration.created_at.isoformat(),
        "updated_at": integration.updated_at.isoformat() if integration.updated_at else None,
        "has_credentials": bool(integration.config_json),
    }


def _load_config(integration: DataSourceIntegration) -> dict[str, Any]:
    if not integration.config_json:
        return {}
    try:
        return json.loads(integration.config_json)
    except json.JSONDecodeError:
        return {}


async def sync_integration(
    db: Session,
    integration: DataSourceIntegration,
    *,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Fetch remote data and update the linked dataset."""
    provider_def = get_provider(integration.provider)
    if not provider_def:
        raise IntegrationFetchError(f"Unknown provider: {integration.provider}")

    config = _load_config(integration)
    integration.status = IntegrationStatus.syncing
    integration.last_sync_error = None
    db.commit()

    try:
        df = await fetch_provider_data(
            integration.provider,
            integration.connection_mode,
            config,
        )
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        integration.status = IntegrationStatus.error
        integration.last_sync_error = str(e)
        db.commit()
        raise

    description = f"Synced from {provider_def['name']} ({trigger})"
    plan_locked = bool(integration.dashboard_plan_locked)

    upload: Optional[Upload] = None
    dataset: Optional[Dataset] = None
    if integration.dataset_id:
        row = get_dataset_upload_in_workspace(db, integration.dataset_id, integration.workspace_id)
        if row:
            dataset, upload = row[0], row[1]

    upload, dataset, _ingestion = ingest_dataframe(
        db,
        df=df,
        workspace_id=integration.workspace_id,
        name=integration.name,
        description=description,
        upload=upload,
        dataset=dataset,
        dashboard_plan_locked=plan_locked,
    )

    integration.dataset_id = dataset.id
    dataset.integration_id = integration.id
    dataset.dashboard_plan_locked = 1 if plan_locked else dataset.dashboard_plan_locked

    now = datetime.utcnow()
    integration.status = IntegrationStatus.active
    integration.last_sync_at = now
    integration.next_sync_at = compute_next_sync_at(integration.refresh_interval_hours, now)
    integration.updated_at = now
    db.commit()
    db.refresh(integration)
    db.refresh(dataset)

    try:
        if trigger == "manual" and integration.dataset_id and upload:
            record_append_snapshot(db, integration.workspace_id, dataset, upload)
        elif trigger == "scheduled" and upload:
            record_upload_snapshot(db, integration.workspace_id, upload, dataset)
    except Exception:
        pass

    analysis_id: Optional[str] = None
    if integration.auto_analyze:
        from services.integration_analysis import run_post_sync_analysis

        analysis_id = run_post_sync_analysis(db, integration.workspace_id, dataset)

    return {
        "integration": integration_to_dict(integration, provider_name=provider_def["name"]),
        "dataset_id": dataset.id,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "analysis_id": analysis_id,
        "dashboard_plan_locked": plan_locked,
    }


def find_due_integrations(db: Session, limit: int = 20) -> list[DataSourceIntegration]:
    now = datetime.utcnow()
    return (
        db.query(DataSourceIntegration)
        .filter(
            DataSourceIntegration.status.in_(
                [IntegrationStatus.active, IntegrationStatus.pending, IntegrationStatus.error]
            ),
            DataSourceIntegration.next_sync_at.isnot(None),
            DataSourceIntegration.next_sync_at <= now,
        )
        .order_by(DataSourceIntegration.next_sync_at.asc())
        .limit(limit)
        .all()
    )
