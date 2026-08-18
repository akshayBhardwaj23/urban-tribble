"""Background scheduler for due integration syncs."""

from __future__ import annotations

import asyncio
import logging

from database import SessionLocal
from services.integration_connectors import IntegrationSyncInProgressError
from services.integration_sync import find_due_integrations, sync_integration

logger = logging.getLogger(__name__)


async def run_due_syncs_once() -> int:
    """Process integrations that are due for refresh. Returns count synced.

    Does not pre-filter on status: a candidate here may include a `syncing`
    row whose heartbeat went stale (see find_due_integrations), and may also
    already have been claimed by a concurrent scheduler or manual refresh by
    the time this reaches it. sync_integration's own atomic claim is what
    decides that, not a status check made here against a snapshot that can be
    out of date the moment it's read.
    """
    db = SessionLocal()
    synced = 0
    try:
        due = find_due_integrations(db)
        for integration in due:
            try:
                await sync_integration(db, integration, trigger="scheduled")
                synced += 1
            except IntegrationSyncInProgressError:
                logger.debug(
                    "Integration %s already claimed by another sync; skipping.",
                    integration.id,
                )
            except Exception as e:
                logger.warning(
                    "Scheduled sync failed for integration %s: %s",
                    integration.id,
                    e,
                )
    finally:
        db.close()
    return synced


async def integration_scheduler_loop(interval_seconds: int) -> None:
    while True:
        try:
            await run_due_syncs_once()
        except Exception:
            logger.exception("Integration scheduler tick failed")
        await asyncio.sleep(interval_seconds)
