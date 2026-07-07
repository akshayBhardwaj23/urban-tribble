from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import require_active_workspace
from models.models import DataSourceIntegration, IntegrationStatus, User
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
    fetch_provider_data,
)
from services.integration_registry import get_provider, list_catalog
from services.integration_sync import (
    compute_next_sync_at,
    integration_to_dict,
    sync_integration,
    find_due_integrations,
)
from services.integration_scheduler import run_due_syncs_once

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class CreateIntegrationBody(BaseModel):
    provider: str
    name: str = Field(min_length=1, max_length=120)
    connection_mode: str = "export_url"
    config: dict[str, Any] = Field(default_factory=dict)
    refresh_interval_hours: int = Field(default=24, ge=1, le=168)
    auto_analyze: bool = True
    dashboard_plan_locked: bool = True
    run_initial_sync: bool = True


class PatchIntegrationBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    connection_mode: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    refresh_interval_hours: Optional[int] = Field(default=None, ge=1, le=168)
    auto_analyze: Optional[bool] = None
    dashboard_plan_locked: Optional[bool] = None


def _validate_connection_mode(provider_id: str, mode: str) -> None:
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(400, f"Unknown provider: {provider_id}")
    modes = {m["id"]: m for m in provider["connection_modes"]}
    if mode not in modes:
        raise HTTPException(400, f"Invalid connection mode for {provider_id}")
    if not modes[mode].get("available", True):
        raise HTTPException(400, f"Connection mode '{mode}' is not available yet for {provider_id}")


@router.get("/catalog")
def get_catalog():
    return {"providers": list_catalog()}


@router.get("/")
def list_integrations(
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    rows = (
        db.query(DataSourceIntegration)
        .filter(DataSourceIntegration.workspace_id == workspace_id)
        .order_by(DataSourceIntegration.created_at.desc())
        .all()
    )
    return [
        integration_to_dict(
            row,
            provider_name=(get_provider(row.provider) or {}).get("name", row.provider),
        )
        for row in rows
    ]


@router.post("/")
async def create_integration(
    body: CreateIntegrationBody,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    provider = get_provider(body.provider)
    if not provider:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    _validate_connection_mode(body.provider, body.connection_mode)

    integration = DataSourceIntegration(
        workspace_id=workspace_id,
        provider=body.provider,
        name=body.name,
        connection_mode=body.connection_mode,
        config_json=json.dumps(body.config),
        refresh_interval_hours=body.refresh_interval_hours or settings.INTEGRATION_DEFAULT_REFRESH_HOURS,
        auto_analyze=1 if body.auto_analyze else 0,
        dashboard_plan_locked=1 if body.dashboard_plan_locked else 0,
        status=IntegrationStatus.pending,
        next_sync_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)

    if body.run_initial_sync:
        try:
            result = await sync_integration(db, integration, trigger="manual")
            return result
        except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
            raise HTTPException(422, str(e)) from e

    return {
        "integration": integration_to_dict(integration, provider_name=provider["name"]),
    }


@router.get("/{integration_id}")
def get_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    integration = (
        db.query(DataSourceIntegration)
        .filter(
            DataSourceIntegration.id == integration_id,
            DataSourceIntegration.workspace_id == workspace_id,
        )
        .first()
    )
    if not integration:
        raise HTTPException(404, "Integration not found")
    provider = get_provider(integration.provider) or {}
    return integration_to_dict(integration, provider_name=provider.get("name"))


@router.patch("/{integration_id}")
def patch_integration(
    integration_id: str,
    body: PatchIntegrationBody,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    integration = (
        db.query(DataSourceIntegration)
        .filter(
            DataSourceIntegration.id == integration_id,
            DataSourceIntegration.workspace_id == workspace_id,
        )
        .first()
    )
    if not integration:
        raise HTTPException(404, "Integration not found")

    if body.name is not None:
        integration.name = body.name
    if body.connection_mode is not None:
        _validate_connection_mode(integration.provider, body.connection_mode)
        integration.connection_mode = body.connection_mode
    if body.config is not None:
        integration.config_json = json.dumps(body.config)
    if body.refresh_interval_hours is not None:
        integration.refresh_interval_hours = body.refresh_interval_hours
        if integration.last_sync_at:
            integration.next_sync_at = compute_next_sync_at(
                body.refresh_interval_hours, integration.last_sync_at
            )
    if body.auto_analyze is not None:
        integration.auto_analyze = 1 if body.auto_analyze else 0
    if body.dashboard_plan_locked is not None:
        integration.dashboard_plan_locked = 1 if body.dashboard_plan_locked else 0

    integration.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(integration)
    provider = get_provider(integration.provider) or {}
    return integration_to_dict(integration, provider_name=provider.get("name"))


@router.delete("/{integration_id}")
def delete_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    integration = (
        db.query(DataSourceIntegration)
        .filter(
            DataSourceIntegration.id == integration_id,
            DataSourceIntegration.workspace_id == workspace_id,
        )
        .first()
    )
    if not integration:
        raise HTTPException(404, "Integration not found")
    db.delete(integration)
    db.commit()
    return {"ok": True, "id": integration_id}


@router.post("/{integration_id}/test")
async def test_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    integration = (
        db.query(DataSourceIntegration)
        .filter(
            DataSourceIntegration.id == integration_id,
            DataSourceIntegration.workspace_id == workspace_id,
        )
        .first()
    )
    if not integration:
        raise HTTPException(404, "Integration not found")
    config = json.loads(integration.config_json) if integration.config_json else {}
    try:
        df = await fetch_provider_data(
            integration.provider,
            integration.connection_mode,
            config,
        )
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        raise HTTPException(422, str(e)) from e
    return {
        "ok": True,
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": [str(c) for c in df.columns[:20]],
    }


@router.post("/{integration_id}/refresh")
async def refresh_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    integration = (
        db.query(DataSourceIntegration)
        .filter(
            DataSourceIntegration.id == integration_id,
            DataSourceIntegration.workspace_id == workspace_id,
        )
        .first()
    )
    if not integration:
        raise HTTPException(404, "Integration not found")
    try:
        return await sync_integration(db, integration, trigger="manual")
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        raise HTTPException(422, str(e)) from e


@router.post("/run-scheduled")
async def run_scheduled_syncs(
    x_integration_cron_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    secret = settings.INTEGRATION_CRON_SECRET
    if secret and x_integration_cron_secret != secret:
        raise HTTPException(403, "Invalid cron secret")
    count = await run_due_syncs_once()
    due_remaining = len(find_due_integrations(db, limit=100))
    return {"synced": count, "due_remaining": due_remaining}
