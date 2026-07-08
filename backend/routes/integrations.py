from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
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
from services.integration_microsoft import (
    _apply_token_payload,
    microsoft_exchange_code_for_tokens,
    microsoft_list_excel_files,
)
from services.integration_oauth import (
    build_microsoft_authorize_url,
    build_signed_state,
    create_oauth_session,
    get_oauth_session,
    microsoft_oauth_configured,
    pop_oauth_session,
    parse_signed_state,
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


class StartOauthBody(BaseModel):
    provider: str
    name: str = Field(min_length=1, max_length=120)
    refresh_interval_hours: int = Field(default=24, ge=1, le=168)
    auto_analyze: bool = True
    dashboard_plan_locked: bool = True


class CompleteMicrosoftOauthBody(BaseModel):
    session_id: str
    item_id: str


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


@router.post("/oauth/start")
def start_integration_oauth(
    body: StartOauthBody,
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    if body.provider != "excel_onedrive":
        raise HTTPException(400, "OAuth start is only wired for Excel / OneDrive right now")
    if not microsoft_oauth_configured():
        raise HTTPException(
            503,
            "Microsoft 365 OAuth is not configured on this deployment yet. "
            "Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and MICROSOFT_REDIRECT_URI.",
        )
    state = build_signed_state(
        {
            "provider": body.provider,
            "workspace_id": workspace_id,
            "user_email": user.email,
            "name": body.name,
            "refresh_interval_hours": body.refresh_interval_hours,
            "auto_analyze": body.auto_analyze,
            "dashboard_plan_locked": body.dashboard_plan_locked,
            "started_at": datetime.utcnow().isoformat(),
        }
    )
    return {
        "authorize_url": build_microsoft_authorize_url(state),
        "provider": body.provider,
    }


@router.get("/oauth/callback/microsoft", response_class=HTMLResponse)
async def microsoft_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    if error:
        return HTMLResponse(
            f"<html><body><h2>Microsoft sign-in failed</h2><p>{error}</p></body></html>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            "<html><body><h2>Missing Microsoft OAuth data</h2>"
            "<p>No code/state was returned.</p></body></html>",
            status_code=400,
        )
    try:
        payload = parse_signed_state(state)
    except ValueError as e:
        return HTMLResponse(
            f"<html><body><h2>Invalid OAuth state</h2><p>{e}</p></body></html>",
            status_code=400,
        )
    try:
        token_payload = await microsoft_exchange_code_for_tokens(code)
        config: dict[str, Any] = {}
        _apply_token_payload(config, token_payload)
        files = await microsoft_list_excel_files(config)
    except IntegrationFetchError as e:
        return HTMLResponse(
            f"<html><body><h2>Microsoft connect failed</h2><p>{e}</p></body></html>",
            status_code=400,
        )

    session_id = create_oauth_session(
        {
            "provider": payload.get("provider", "excel_onedrive"),
            "workspace_id": payload["workspace_id"],
            "user_email": payload["user_email"],
            "name": payload["name"],
            "refresh_interval_hours": payload["refresh_interval_hours"],
            "auto_analyze": payload["auto_analyze"],
            "dashboard_plan_locked": payload["dashboard_plan_locked"],
            "config": config,
            "files": files,
        }
    )
    redirect_to = f"{settings.FRONTEND_APP_URL.rstrip('/')}/integrations?oauth_session={quote(session_id)}"
    return RedirectResponse(url=redirect_to, status_code=303)


@router.get("/oauth/session/{session_id}")
def get_integration_oauth_session(
    session_id: str,
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    session = get_oauth_session(session_id)
    if not session:
        raise HTTPException(404, "OAuth session not found or expired")
    if session.get("workspace_id") != workspace_id or session.get("user_email") != user.email:
        raise HTTPException(403, "OAuth session does not belong to this workspace")
    return {
        "session_id": session_id,
        "provider": session["provider"],
        "name": session["name"],
        "refresh_interval_hours": session["refresh_interval_hours"],
        "auto_analyze": session["auto_analyze"],
        "dashboard_plan_locked": session["dashboard_plan_locked"],
        "files": session.get("files", []),
    }


@router.post("/oauth/complete/microsoft")
async def complete_microsoft_oauth(
    body: CompleteMicrosoftOauthBody,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    session = pop_oauth_session(body.session_id)
    if not session:
        raise HTTPException(404, "OAuth session not found or expired")
    if session.get("workspace_id") != workspace_id or session.get("user_email") != user.email:
        raise HTTPException(403, "OAuth session does not belong to this workspace")
    selected = next((f for f in session.get("files", []) if f.get("id") == body.item_id), None)
    if not selected:
        raise HTTPException(404, "Selected workbook not found in OAuth session")

    config = dict(session.get("config") or {})
    config.update(
        {
            "item_id": selected["id"],
            "item_name": selected.get("name"),
            "web_url": selected.get("web_url"),
        }
    )
    integration = DataSourceIntegration(
        workspace_id=workspace_id,
        provider="excel_onedrive",
        name=str(session["name"]).strip() or selected.get("name") or "Excel / OneDrive data",
        connection_mode="oauth",
        config_json=json.dumps(config),
        refresh_interval_hours=int(session["refresh_interval_hours"]) or settings.INTEGRATION_DEFAULT_REFRESH_HOURS,
        auto_analyze=1 if session["auto_analyze"] else 0,
        dashboard_plan_locked=1 if session["dashboard_plan_locked"] else 0,
        status=IntegrationStatus.pending,
        next_sync_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)

    try:
        return await sync_integration(db, integration, trigger="manual")
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        raise HTTPException(422, str(e)) from e


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
