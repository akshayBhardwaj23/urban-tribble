"""Run integration sync, preserve dashboard layout, and trigger analysis.

Concurrency model: exactly one caller may hold a row in `syncing` at a time.
`claim_integration_for_sync` is a single conditional UPDATE (a compare-and-swap
on `status`), so it is safe under concurrent callers on both SQLite and
Postgres without needing `SELECT ... FOR UPDATE SKIP LOCKED` -- two callers
racing to claim the same row always leave exactly one of them with rowcount 1.
A `syncing` row whose heartbeat (`syncing_started_at`) is older than
`INTEGRATION_STALE_SYNC_MINUTES` is treated as abandoned (crashed worker, killed
process) and is claimable again, so a crash cannot brick a connection forever.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session

from config import settings
from models.models import (
    Dataset,
    DataSourceIntegration,
    IntegrationStatus,
    Upload,
)
from services.ingest_pipeline import ingest_dataframe
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
    IntegrationSyncInProgressError,
    fetch_provider_data,
    remote_change_stamp,
)
from services.integration_credentials import decrypt_config, encrypt_config
from services.integration_registry import get_provider
from services.subscription_usage import assert_upload_allowed
from services.upload_worker import get_executor
from services.workspace_query import get_dataset_upload_in_workspace, workspace_owner
from services.workspace_timeline import record_append_snapshot, record_upload_snapshot

logger = logging.getLogger(__name__)


def _clamp_refresh_hours(hours: int) -> int:
    return max(
        settings.INTEGRATION_MIN_REFRESH_HOURS,
        min(hours, settings.INTEGRATION_MAX_REFRESH_HOURS),
    )


def compute_next_sync_at(refresh_hours: int, from_time: datetime | None = None) -> datetime:
    base = from_time or datetime.utcnow()
    return base + timedelta(hours=_clamp_refresh_hours(refresh_hours))


def integration_to_dict(
    integration: DataSourceIntegration,
    *,
    provider_name: str | None = None,
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
    """Decrypt stored credentials. Raises IntegrationCredentialsError when the
    row is encrypted but unreadable; called inside sync_integration's fetch
    try/except so that failure is recorded like any other fetch failure."""
    return decrypt_config(integration.config_json)


def count_workspace_integrations(db: Session, workspace_id: str) -> int:
    return int(
        db.query(func.count(DataSourceIntegration.id))
        .filter(DataSourceIntegration.workspace_id == workspace_id)
        .scalar()
        or 0
    )


def _stale_cutoff(now: datetime | None = None) -> datetime:
    now = now or datetime.utcnow()
    return now - timedelta(minutes=max(1, int(settings.INTEGRATION_STALE_SYNC_MINUTES)))


def claim_integration_for_sync(db: Session, integration_id: str) -> bool:
    """Atomically transition a row to `syncing`, unless it is already syncing
    and its heartbeat is still fresh. Returns True iff this call won the claim.

    A single conditional UPDATE, not a read-then-write: the row's real status
    at write time is what the database's own row lock decides, so two
    concurrent callers can never both observe rowcount 1 for the same row.
    """
    now = datetime.utcnow()
    result = db.execute(
        update(DataSourceIntegration)
        .where(
            DataSourceIntegration.id == integration_id,
            DataSourceIntegration.status != IntegrationStatus.disconnected,
            or_(
                DataSourceIntegration.status != IntegrationStatus.syncing,
                DataSourceIntegration.syncing_started_at.is_(None),
                DataSourceIntegration.syncing_started_at <= _stale_cutoff(now),
            ),
        )
        .values(
            status=IntegrationStatus.syncing,
            syncing_started_at=now,
            last_sync_error=None,
        )
    )
    db.commit()
    return result.rowcount == 1


def _mark_sync_failed(db: Session, integration: DataSourceIntegration, message: str) -> None:
    integration.status = IntegrationStatus.error
    integration.last_sync_error = message[:2000]
    integration.syncing_started_at = None
    integration.updated_at = datetime.utcnow()
    db.commit()


def _finish_unchanged_sync(
    db: Session,
    integration: DataSourceIntegration,
    provider_def: dict[str, Any],
) -> dict[str, Any]:
    """Close out a sync that had nothing to do.

    The source is healthy and on schedule, so it is released exactly as a real
    sync would release it -- active, heartbeat cleared, next run booked. The
    dataset is deliberately untouched: re-writing identical rows would churn
    the cache and move `last_sync_at` in a way that reads as new data arriving.
    """
    now = datetime.utcnow()
    integration.status = IntegrationStatus.active
    integration.next_sync_at = compute_next_sync_at(integration.refresh_interval_hours, now)
    integration.syncing_started_at = None
    integration.last_sync_error = None
    integration.updated_at = now
    db.commit()
    db.refresh(integration)
    return {
        "integration": integration_to_dict(integration, provider_name=provider_def["name"]),
        "dataset_id": integration.dataset_id,
        "row_count": None,
        "column_count": None,
        "analysis_id": None,
        "analysis_skipped_reason": None,
        "dashboard_plan_locked": bool(integration.dashboard_plan_locked),
        "skipped": True,
        "skipped_reason": "The source has not changed since the last sync.",
    }


def _plan_limit_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict) and detail.get("message"):
        return str(detail["message"])
    return "Plan limit reached."


async def sync_integration(
    db: Session,
    integration: DataSourceIntegration,
    *,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Fetch remote data and update the linked dataset.

    Raises IntegrationSyncInProgressError without touching the row at all when
    another caller already holds the claim. Every other failure path leaves
    the row in `error` with a readable `last_sync_error` -- never stuck in
    `syncing` -- so "Refresh now" and the scheduler can always recover it.
    """
    provider_def = get_provider(integration.provider)
    if not provider_def:
        raise IntegrationFetchError(f"Unknown provider: {integration.provider}")

    if not claim_integration_for_sync(db, integration.id):
        raise IntegrationSyncInProgressError(
            "This connection is already syncing. Try again in a moment."
        )
    db.refresh(integration)

    is_first_sync = integration.dataset_id is None
    if is_first_sync:
        # Only the first sync of a new connection creates a new Upload row;
        # every later refresh reuses it. Check before spending a network call
        # and an LLM pass on data that will just be discarded.
        user = workspace_owner(db, integration.workspace_id)
        if user is not None:
            try:
                assert_upload_allowed(db, user, integration.workspace_id)
            except HTTPException as e:
                message = _plan_limit_message(e)
                _mark_sync_failed(db, integration, message)
                raise IntegrationNotConfiguredError(message) from e

    try:
        config = _load_config(integration)

        # A scheduled refresh of a source nobody has edited would otherwise
        # re-download, re-clean and re-cache the whole thing on every tick.
        # One cheap metadata call avoids all of it. Only for scheduled runs:
        # someone who clicks "Refresh now" gets a real fetch, because being
        # told "nothing happened" is a worse answer than doing the work.
        stamp = None
        if trigger == "scheduled":
            stamp = await remote_change_stamp(
                integration.provider, integration.connection_mode, config
            )
            if stamp and config.get("last_change_stamp") == stamp:
                return _finish_unchanged_sync(db, integration, provider_def)

        df = await fetch_provider_data(
            integration.provider,
            integration.connection_mode,
            config,
        )
        if stamp:
            config["last_change_stamp"] = stamp
        # Providers that rotate tokens (Microsoft) mutate `config` during fetch.
        integration.config_json = encrypt_config(config)
        db.commit()
    except (IntegrationFetchError, IntegrationNotConfiguredError) as e:
        _mark_sync_failed(db, integration, str(e))
        raise

    description = f"Synced from {provider_def['name']} ({trigger})"
    plan_locked = bool(integration.dashboard_plan_locked)

    upload: Upload | None = None
    dataset: Dataset | None = None
    if integration.dataset_id:
        row = get_dataset_upload_in_workspace(db, integration.dataset_id, integration.workspace_id)
        if row:
            dataset, upload = row[0], row[1]

    try:
        loop = asyncio.get_running_loop()
        upload, dataset, _ingestion = await loop.run_in_executor(
            get_executor(),
            functools.partial(
                ingest_dataframe,
                db,
                df=df,
                workspace_id=integration.workspace_id,
                name=integration.name,
                description=description,
                upload=upload,
                dataset=dataset,
                dashboard_plan_locked=plan_locked,
            ),
        )
    except Exception as e:
        # Cleaning, column detection, dashboard planning, and the frame-size
        # cap all run inside this call. None of it is wrapped upstream, so
        # without this the row would be left in `syncing` on any failure here.
        _mark_sync_failed(
            db, integration, f"Sync fetched data but failed while processing it: {e}"
        )
        raise

    integration.dataset_id = dataset.id
    dataset.integration_id = integration.id
    dataset.dashboard_plan_locked = 1 if plan_locked else dataset.dashboard_plan_locked

    now = datetime.utcnow()
    integration.status = IntegrationStatus.active
    integration.last_sync_at = now
    integration.next_sync_at = compute_next_sync_at(integration.refresh_interval_hours, now)
    integration.syncing_started_at = None
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
        logger.exception("Timeline snapshot failed for integration %s", integration.id)

    analysis_id: str | None = None
    analysis_skipped_reason: str | None = None
    if integration.auto_analyze:
        from services.integration_analysis import run_post_sync_analysis

        try:
            analysis_id, analysis_skipped_reason = await loop.run_in_executor(
                get_executor(),
                functools.partial(
                    run_post_sync_analysis, db, integration.workspace_id, dataset
                ),
            )
        except Exception:
            logger.exception("Post-sync analysis failed for integration %s", integration.id)
            analysis_skipped_reason = "Briefing failed to generate; the sync itself succeeded."

    return {
        "integration": integration_to_dict(integration, provider_name=provider_def["name"]),
        "dataset_id": dataset.id,
        "row_count": upload.row_count,
        "column_count": upload.column_count,
        "analysis_id": analysis_id,
        "analysis_skipped_reason": analysis_skipped_reason,
        "dashboard_plan_locked": plan_locked,
        "skipped": False,
        "skipped_reason": None,
    }


def find_due_integrations(db: Session, limit: int = 20) -> list[DataSourceIntegration]:
    """Rows ready for a sync attempt: normally-due rows, plus any `syncing`
    row whose heartbeat has gone stale (crashed mid-sync). Listing a stale
    `syncing` row here does not claim it -- `sync_integration` still has to
    win `claim_integration_for_sync` before touching it, so this is safe to
    call from multiple schedulers without coordination.
    """
    now = datetime.utcnow()
    return (
        db.query(DataSourceIntegration)
        .filter(
            DataSourceIntegration.next_sync_at.isnot(None),
            DataSourceIntegration.next_sync_at <= now,
            or_(
                DataSourceIntegration.status.in_(
                    [IntegrationStatus.active, IntegrationStatus.pending, IntegrationStatus.error]
                ),
                and_(
                    DataSourceIntegration.status == IntegrationStatus.syncing,
                    or_(
                        DataSourceIntegration.syncing_started_at.is_(None),
                        DataSourceIntegration.syncing_started_at <= _stale_cutoff(now),
                    ),
                ),
            ),
        )
        .order_by(DataSourceIntegration.next_sync_at.asc())
        .limit(limit)
        .all()
    )
