from __future__ import annotations

import hmac
import html
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from deps import require_active_workspace
from models.models import DataSourceIntegration, IntegrationStatus, User
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
    IntegrationSyncInProgressError,
    fetch_provider_data,
)
from services.integration_credentials import decrypt_config, encrypt_config
from services.integration_google import (
    _apply_token_payload as _apply_google_token_payload,
)
from services.integration_google import (
    build_google_authorize_url,
    default_tab_name,
    google_exchange_code_for_tokens,
    google_list_sheet_tabs,
    google_list_spreadsheets,
    google_oauth_configured,
    tab_choice_is_ambiguous,
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
    parse_signed_state,
    pop_oauth_session,
)
from services.integration_registry import get_provider, list_catalog, provider_enabled
from services.integration_scheduler import run_due_syncs_once
from services.integration_sync import (
    auto_sync_enabled,
    count_workspace_integrations,
    find_due_integrations,
    initial_next_sync_at,
    integration_to_dict,
    next_sync_at_for,
    sync_integration,
)
from services.upload_rate_limit import check_integration_fetch_rate_limit

logger = logging.getLogger(__name__)

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
    name: str | None = Field(default=None, min_length=1, max_length=120)
    connection_mode: str | None = None
    config: dict[str, Any] | None = None
    refresh_interval_hours: int | None = Field(default=None, ge=1, le=168)
    auto_analyze: bool | None = None
    dashboard_plan_locked: bool | None = None


class StartOauthBody(BaseModel):
    provider: str
    name: str = Field(min_length=1, max_length=120)
    refresh_interval_hours: int = Field(default=24, ge=1, le=168)
    auto_analyze: bool = True
    dashboard_plan_locked: bool = True


class CompleteMicrosoftOauthBody(BaseModel):
    session_id: str
    item_id: str


class CompleteGoogleOauthBody(BaseModel):
    session_id: str
    # Several sheets can be connected from a single sign-in; each becomes its
    # own source with its own dashboard and refresh schedule.
    item_ids: list[str] = Field(min_length=1, max_length=20)
    # Chosen tab per file, for workbooks where more than one tab looks like
    # data. Files left out fall back to the reader's own auto-pick.
    sheet_names: dict[str, str] = Field(default_factory=dict)


class InspectGoogleTabsBody(BaseModel):
    session_id: str
    item_ids: list[str] = Field(min_length=1, max_length=20)


class UpdateIntegrationSheetBody(BaseModel):
    sheet_name: str = Field(min_length=1, max_length=200)


def _require_integrations_enabled() -> None:
    if not settings.INTEGRATIONS_ENABLED:
        raise HTTPException(
            503,
            "Live integrations are coming soon. Import a CSV or Excel file for now.",
        )


def _require_workspace_capacity(db: Session, workspace_id: str) -> None:
    cap = int(settings.INTEGRATION_MAX_PER_WORKSPACE)
    if cap and count_workspace_integrations(db, workspace_id) >= cap:
        raise HTTPException(
            400,
            f"This workspace has reached the limit of {cap} connected sources. "
            "Remove one before connecting another.",
        )


def _require_provider_offered(provider_id: str) -> None:
    """Refuse providers outside the shipped wave.

    The catalog already reports these as unavailable; this is the same check on
    the write path, so the UI and the API cannot disagree and a request made by
    hand gets the same answer as the button would.
    """
    if not provider_enabled(provider_id):
        raise HTTPException(
            400,
            f"{provider_id} is not available to connect yet.",
        )


def _validate_connection_mode(provider_id: str, mode: str) -> None:
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(400, f"Unknown provider: {provider_id}")
    _require_provider_offered(provider_id)
    modes = {m["id"]: m for m in provider["connection_modes"]}
    if mode not in modes:
        raise HTTPException(400, f"Invalid connection mode for {provider_id}")
    if not modes[mode].get("available", True):
        raise HTTPException(400, f"Connection mode '{mode}' is not available yet for {provider_id}")


@router.get("/catalog")
def get_catalog():
    return {
        "providers": list_catalog(),
        "enabled": settings.INTEGRATIONS_ENABLED,
    }


@router.post("/oauth/start")
def start_integration_oauth(
    body: StartOauthBody,
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _require_integrations_enabled()
    user, workspace_id = ws
    _require_provider_offered(body.provider)

    if body.provider == "excel_onedrive":
        if not microsoft_oauth_configured():
            raise HTTPException(
                503,
                "Microsoft 365 OAuth is not configured on this deployment yet. "
                "Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and MICROSOFT_REDIRECT_URI.",
            )
        build_authorize_url = build_microsoft_authorize_url
    elif body.provider == "google_sheets":
        if not google_oauth_configured():
            raise HTTPException(
                503,
                "Google OAuth is not configured on this deployment yet. "
                "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI.",
            )
        build_authorize_url = build_google_authorize_url
    else:
        raise HTTPException(
            400, f"OAuth sign-in is not available for {body.provider} yet."
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
        "authorize_url": build_authorize_url(state),
        "provider": body.provider,
    }


@router.get("/oauth/callback/microsoft", response_class=HTMLResponse)
async def microsoft_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        safe = html.escape(str(error)[:300])
        return HTMLResponse(
            f"<html><body><h2>Microsoft sign-in failed</h2><p>{safe}</p></body></html>",
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
        safe = html.escape(str(e)[:300])
        return HTMLResponse(
            f"<html><body><h2>Invalid OAuth state</h2><p>{safe}</p></body></html>",
            status_code=400,
        )
    try:
        token_payload = await microsoft_exchange_code_for_tokens(code)
        config: dict[str, Any] = {}
        _apply_token_payload(config, token_payload)
        files = await microsoft_list_excel_files(config)
    except IntegrationFetchError as e:
        safe = html.escape(str(e)[:300])
        return HTMLResponse(
            f"<html><body><h2>Microsoft connect failed</h2><p>{safe}</p></body></html>",
            status_code=400,
        )

    try:
        session_id = create_oauth_session(
            db,
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
            },
        )
    except SQLAlchemyError:
        # Most likely the workspace was removed while the consent screen was
        # open, so the session has nowhere to belong. This lands in a browser
        # redirect, so it has to render, not raise.
        db.rollback()
        logger.exception("Could not persist Microsoft OAuth session")
        return HTMLResponse(
            "<html><body><h2>Could not finish connecting</h2>"
            "<p>That workspace is no longer available. "
            "Start the connection again from Integrations.</p></body></html>",
            status_code=400,
        )
    redirect_to = f"{settings.FRONTEND_APP_URL.rstrip('/')}/integrations?oauth_session={quote(session_id)}"
    return RedirectResponse(url=redirect_to, status_code=303)


@router.get("/oauth/callback/google", response_class=HTMLResponse)
async def google_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        safe = html.escape(str(error)[:300])
        return HTMLResponse(
            f"<html><body><h2>Google sign-in failed</h2><p>{safe}</p></body></html>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            "<html><body><h2>Missing Google OAuth data</h2>"
            "<p>No code/state was returned.</p></body></html>",
            status_code=400,
        )
    try:
        payload = parse_signed_state(state)
    except ValueError as e:
        safe = html.escape(str(e)[:300])
        return HTMLResponse(
            f"<html><body><h2>Invalid OAuth state</h2><p>{safe}</p></body></html>",
            status_code=400,
        )
    try:
        token_payload = await google_exchange_code_for_tokens(code)
        config: dict[str, Any] = {}
        _apply_google_token_payload(config, token_payload)
        files = await google_list_spreadsheets(config)
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        safe = html.escape(str(e)[:300])
        return HTMLResponse(
            f"<html><body><h2>Google connect failed</h2><p>{safe}</p></body></html>",
            status_code=400,
        )

    try:
        session_id = create_oauth_session(
            db,
            {
                "provider": "google_sheets",
                "workspace_id": payload["workspace_id"],
                "user_email": payload["user_email"],
                "name": payload["name"],
                "refresh_interval_hours": payload["refresh_interval_hours"],
                "auto_analyze": payload["auto_analyze"],
                "dashboard_plan_locked": payload["dashboard_plan_locked"],
                "config": config,
                "files": files,
            },
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not persist Google OAuth session")
        return HTMLResponse(
            "<html><body><h2>Could not finish connecting</h2>"
            "<p>That workspace is no longer available. "
            "Start the connection again from Integrations.</p></body></html>",
            status_code=400,
        )

    redirect_to = (
        f"{settings.FRONTEND_APP_URL.rstrip('/')}/integrations"
        f"?oauth_session={quote(session_id)}"
    )
    return RedirectResponse(url=redirect_to, status_code=303)


async def _sync_new_integrations(integration_ids: list[str]) -> None:
    """Sync freshly-connected sources after the response has been sent.

    Runs on its own session because the request's session is closed by the
    time this executes. Each source is independent: one failing must not stop
    the rest, and sync_integration has already recorded the reason on the row,
    so there is nothing to propagate here.
    """
    db = SessionLocal()
    try:
        for integration_id in integration_ids:
            row = (
                db.query(DataSourceIntegration)
                .filter(DataSourceIntegration.id == integration_id)
                .first()
            )
            if row is None:
                continue
            try:
                await sync_integration(db, row, trigger="manual")
            except Exception:
                logger.warning(
                    "Initial sync failed for new integration %s", integration_id
                )
    finally:
        db.close()


@router.post("/oauth/tabs/google")
async def inspect_google_tabs(
    body: InspectGoogleTabsBody,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Which tab each selected workbook would use, and whether to ask.

    Read-only and does not consume the sign-in, so the user can still change
    their file selection afterwards. Only workbooks where more than one tab
    looks like a data table are worth interrupting for; everything else
    reports its auto-pick so the client can connect it without a question.
    """
    _require_integrations_enabled()
    user, workspace_id = ws

    session = get_oauth_session(db, body.session_id)
    if not session:
        raise HTTPException(404, "OAuth session not found or expired")
    if session.get("workspace_id") != workspace_id or session.get("user_email") != user.email:
        raise HTTPException(403, "OAuth session does not belong to this workspace")

    files_by_id = {f.get("id"): f for f in session.get("files", []) if f.get("id")}
    base_config = dict(session.get("config") or {})

    results: list[dict[str, Any]] = []
    for item_id in body.item_ids:
        entry = files_by_id.get(item_id)
        if not entry:
            continue
        config = {
            **base_config,
            "item_id": entry["id"],
            "item_name": entry.get("name"),
            "mime_type": entry.get("mime_type"),
        }
        try:
            tabs = await google_list_sheet_tabs(config)
        except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
            # Inspecting is a convenience: a workbook we cannot read the tabs
            # of should still be connectable, falling back to the auto-pick.
            logger.info("Could not list tabs for %s: %s", item_id, e)
            tabs = []
        results.append(
            {
                "item_id": entry["id"],
                "name": entry.get("name"),
                "tabs": tabs,
                "needs_choice": tab_choice_is_ambiguous(tabs),
                "suggested_tab": default_tab_name(tabs),
            }
        )

    return {"files": results}


@router.post("/oauth/complete/google")
def complete_google_oauth(
    body: CompleteGoogleOauthBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Connect one or more Google spreadsheets from a single sign-in.

    Returns as soon as the sources exist, with the first sync running in the
    background. Syncing several sheets inline would mean a request holding open
    for minutes -- each sync cleans, profiles and (on a first sync) calls the
    model. Clients poll GET /api/integrations for status to move off `pending`.
    """
    _require_integrations_enabled()
    user, workspace_id = ws

    session = pop_oauth_session(db, body.session_id)
    if not session:
        raise HTTPException(404, "OAuth session not found or expired")
    if session.get("workspace_id") != workspace_id or session.get("user_email") != user.email:
        raise HTTPException(403, "OAuth session does not belong to this workspace")

    files_by_id = {f.get("id"): f for f in session.get("files", []) if f.get("id")}
    selected = [files_by_id[i] for i in body.item_ids if i in files_by_id]
    missing = [i for i in body.item_ids if i not in files_by_id]
    if missing:
        raise HTTPException(
            404,
            f"{len(missing)} selected file(s) were not part of this sign-in. "
            "Start the connection again.",
        )

    # Check the whole batch up front: connecting three of five and then failing
    # would leave the user to work out which ones landed.
    cap = int(settings.INTEGRATION_MAX_PER_WORKSPACE)
    if cap:
        existing = count_workspace_integrations(db, workspace_id)
        if existing + len(selected) > cap:
            raise HTTPException(
                400,
                f"Connecting {len(selected)} more source(s) would exceed the limit "
                f"of {cap} for this workspace ({existing} already connected). "
                "Select fewer, or remove an existing source first.",
            )

    base_config = dict(session.get("config") or {})
    base_name = str(session.get("name") or "").strip()
    created: list[dict[str, Any]] = []

    for entry in selected:
        config = dict(base_config)
        config.update(
            {
                "item_id": entry["id"],
                "item_name": entry.get("name"),
                "mime_type": entry.get("mime_type"),
                "web_url": entry.get("web_url"),
            }
        )
        chosen_tab = (body.sheet_names.get(entry["id"]) or "").strip()
        if chosen_tab:
            config["sheet_name"] = chosen_tab
        # With several sheets in one go, the user's single display name would
        # collide across all of them; the file's own name is more useful.
        display_name = entry.get("name") or base_name or "Google Sheets data"
        if len(selected) == 1 and base_name:
            display_name = base_name

        integration = DataSourceIntegration(
            workspace_id=workspace_id,
            provider="google_sheets",
            name=display_name[:120],
            connection_mode="oauth",
            config_json=encrypt_config(config),
            refresh_interval_hours=int(session["refresh_interval_hours"])
            or settings.INTEGRATION_DEFAULT_REFRESH_HOURS,
            auto_analyze=1 if session["auto_analyze"] else 0,
            dashboard_plan_locked=1 if session["dashboard_plan_locked"] else 0,
            status=IntegrationStatus.pending,
            next_sync_at=initial_next_sync_at(),
        )
        db.add(integration)
        db.flush()
        created.append(integration_to_dict(integration, provider_name="Google Sheets"))

    db.commit()

    background_tasks.add_task(_sync_new_integrations, [c["id"] for c in created])

    return {
        "connected": len(created),
        "integrations": created,
        "syncing": True,
    }


@router.get("/oauth/session/{session_id}")
def get_integration_oauth_session(
    session_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    user, workspace_id = ws
    session = get_oauth_session(db, session_id)
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
    _require_integrations_enabled()
    user, workspace_id = ws
    session = pop_oauth_session(db, body.session_id)
    if not session:
        raise HTTPException(404, "OAuth session not found or expired")
    if session.get("workspace_id") != workspace_id or session.get("user_email") != user.email:
        raise HTTPException(403, "OAuth session does not belong to this workspace")
    selected = next((f for f in session.get("files", []) if f.get("id") == body.item_id), None)
    if not selected:
        raise HTTPException(404, "Selected workbook not found in OAuth session")

    _require_workspace_capacity(db, workspace_id)

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
        config_json=encrypt_config(config),
        refresh_interval_hours=int(session["refresh_interval_hours"]) or settings.INTEGRATION_DEFAULT_REFRESH_HOURS,
        auto_analyze=1 if session["auto_analyze"] else 0,
        dashboard_plan_locked=1 if session["dashboard_plan_locked"] else 0,
        status=IntegrationStatus.pending,
        next_sync_at=initial_next_sync_at(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)

    try:
        return await sync_integration(db, integration, trigger="manual")
    except IntegrationSyncInProgressError as e:
        raise HTTPException(409, str(e)) from e
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
    _require_integrations_enabled()
    _, workspace_id = ws
    provider = get_provider(body.provider)
    if not provider:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    _validate_connection_mode(body.provider, body.connection_mode)
    _require_workspace_capacity(db, workspace_id)

    integration = DataSourceIntegration(
        workspace_id=workspace_id,
        provider=body.provider,
        name=body.name,
        connection_mode=body.connection_mode,
        config_json=encrypt_config(body.config),
        refresh_interval_hours=body.refresh_interval_hours or settings.INTEGRATION_DEFAULT_REFRESH_HOURS,
        auto_analyze=1 if body.auto_analyze else 0,
        dashboard_plan_locked=1 if body.dashboard_plan_locked else 0,
        status=IntegrationStatus.pending,
        next_sync_at=initial_next_sync_at(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)

    if body.run_initial_sync:
        try:
            result = await sync_integration(db, integration, trigger="manual")
            return result
        except IntegrationSyncInProgressError as e:
            raise HTTPException(409, str(e)) from e
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
    _require_integrations_enabled()
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
        integration.config_json = encrypt_config(body.config)
    if body.refresh_interval_hours is not None:
        integration.refresh_interval_hours = body.refresh_interval_hours
        if integration.last_sync_at:
            integration.next_sync_at = next_sync_at_for(
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


@router.post("/{integration_id}/sheet")
async def update_integration_sheet(
    integration_id: str,
    body: UpdateIntegrationSheetBody,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Point an existing source at a different tab, then re-read it.

    Deliberately not part of PATCH /{id}: that replaces `config` wholesale,
    which for an OAuth source would discard the stored access and refresh
    tokens and break the connection. This merges a single key instead.

    Re-syncs immediately because the dashboard was built from the old tab's
    columns; leaving it in place would show numbers from a tab the source no
    longer reads.
    """
    _require_integrations_enabled()
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
        config = decrypt_config(integration.config_json)
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        raise HTTPException(422, str(e)) from e

    config["sheet_name"] = body.sheet_name.strip()
    # The stored change marker refers to content already read from the old tab;
    # clearing it stops the unchanged-source check from skipping this re-read.
    config.pop("last_change_stamp", None)
    integration.config_json = encrypt_config(config)
    db.commit()

    try:
        return await sync_integration(db, integration, trigger="manual")
    except IntegrationSyncInProgressError as e:
        raise HTTPException(409, str(e)) from e
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        raise HTTPException(422, str(e)) from e


@router.get("/{integration_id}/tabs")
async def list_integration_tabs(
    integration_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Tabs available to an already-connected source, for changing the choice."""
    _require_integrations_enabled()
    user, workspace_id = ws
    # Listing tabs for an uploaded .xlsx downloads the whole workbook, so this
    # is a provider fetch like any other, not a cheap metadata read.
    check_integration_fetch_rate_limit(db, user.email)
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
    if integration.provider != "google_sheets":
        raise HTTPException(400, "Tab selection is only available for Google Sheets.")

    try:
        config = decrypt_config(integration.config_json)
        tabs = await google_list_sheet_tabs(config)
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        raise HTTPException(422, str(e)) from e

    return {
        "tabs": tabs,
        "current_tab": config.get("sheet_name"),
        "suggested_tab": default_tab_name(tabs),
    }


@router.post("/{integration_id}/test")
async def test_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _require_integrations_enabled()
    user, workspace_id = ws
    check_integration_fetch_rate_limit(db, user.email)
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
        config = decrypt_config(integration.config_json)
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
    _require_integrations_enabled()
    user, workspace_id = ws
    # A refresh downloads the source again and, with auto_analyze on, spends a
    # model call. Only the first sync of a connection costs an upload credit,
    # so the plan caps alone leave this endpoint effectively unbounded.
    check_integration_fetch_rate_limit(db, user.email)
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
    except IntegrationSyncInProgressError as e:
        raise HTTPException(409, str(e)) from e
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        raise HTTPException(422, str(e)) from e


@router.post("/run-scheduled")
async def run_scheduled_syncs(
    x_integration_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_integrations_enabled()
    secret = (settings.INTEGRATION_CRON_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            503,
            "Integration cron is disabled until INTEGRATION_CRON_SECRET is configured.",
        )
    provided = (x_integration_cron_secret or "").strip()
    if not provided or not hmac.compare_digest(provided, secret):
        raise HTTPException(403, "Invalid cron secret")
    if not auto_sync_enabled():
        # A cron may already be pointed here. Answer plainly rather than
        # failing, so an operator sees why nothing is happening.
        return {
            "synced": 0,
            "due_remaining": 0,
            "auto_sync_enabled": False,
            "detail": (
                "Unattended syncing is off (INTEGRATION_AUTO_SYNC_ENABLED=false). "
                "Sources refresh only when a user asks."
            ),
        }
    count = await run_due_syncs_once()
    due_remaining = len(find_due_integrations(db, limit=100))
    return {"synced": count, "due_remaining": due_remaining, "auto_sync_enabled": True}
