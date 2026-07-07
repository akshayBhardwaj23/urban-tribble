"""Background scheduler for due integration syncs."""

from __future__ import annotations

import asyncio
import logging

from database import SessionLocal
from models.models import DataSourceIntegration, IntegrationStatus
from services.integration_sync import find_due_integrations, sync_integration

logger = logging.getLogger(__name__)


async def run_due_syncs_once() -> int:
    """Process integrations that are due for refresh. Returns count synced."""
    db = SessionLocal()
    synced = 0
    try:
        due = find_due_integrations(db)
        for integration in due:
            if integration.status == IntegrationStatus.syncing:
                continue
            try:
                await sync_integration(db, integration, trigger="scheduled")
                synced += 1
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
