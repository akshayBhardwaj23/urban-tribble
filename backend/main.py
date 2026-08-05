import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

import observability
from config import collect_runtime_setting_errors, settings, validate_runtime_settings
from database import Base, SessionLocal, engine
from models import models as _models  # noqa: F401 — register ORM tables for create_all
from routes import (
    analysis,
    auth,
    billing,
    chat,
    dashboards,
    datasets,
    integrations,
    relations,
    summaries,
    uploads,
    workspace_timeline,
    workspaces,
)
from schemas import HealthResponse
from services import storage

logger = logging.getLogger(__name__)


def _cors_allow_origins() -> list[str]:
    return [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]


def _run_migrations() -> None:
    """Bring the schema to head.

    Databases created before Alembic existed are stamped at the baseline first;
    revision 0002 is idempotent and fills in whatever they are missing.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext

    cfg = Config(str(Path(__file__).parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))

    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
        legacy = current is None and inspect(engine).has_table("users")

    if legacy:
        logger.info("Existing pre-Alembic database detected; stamping baseline.")
        command.stamp(cfg, "0001_baseline")

    command.upgrade(cfg, "head")


def _backfill_upload_workspace_ids() -> None:
    """Assign uploads with NULL workspace_id (legacy rows) to a plausible workspace.

    Older builds never set ``Upload.workspace_id``. The API now scopes by workspace,
    so NULL rows are invisible everywhere.

    Heuristic (multi-account DBs): attribute each orphan to the **first workspace**
    (by ``created_at``) of the **most recently registered user who already existed**
    when the upload was recorded. Uploads that predate every user go to the **earliest**
    user's first workspace. This matches typical dev DBs where a second account was
    added later and all pre-existing uploads belonged to the first account.

    Single-account installs: same rule uses the owner's first workspace (not whichever
    workspace is currently active), so legacy data stays on the original workspace.
    """
    from models.models import Upload, User, Workspace

    db = SessionLocal()
    try:
        if db.query(Upload).filter(Upload.workspace_id.is_(None)).count() == 0:
            return

        users = db.query(User).order_by(User.created_at.asc()).all()
        if not users:
            return

        user_first_workspace: List[Tuple[datetime, str]] = []
        for u in users:
            ws = (
                db.query(Workspace)
                .filter(Workspace.owner_id == u.id)
                .order_by(Workspace.created_at.asc())
                .first()
            )
            if ws:
                user_first_workspace.append((u.created_at, ws.id))

        if not user_first_workspace:
            return

        orphans = (
            db.query(Upload)
            .filter(Upload.workspace_id.is_(None))
            .order_by(Upload.created_at.asc())
            .all()
        )
        default_ws = user_first_workspace[0][1]

        for up in orphans:
            chosen = default_ws
            for user_created_at, ws_id in reversed(user_first_workspace):
                if up.created_at >= user_created_at:
                    chosen = ws_id
                    break
            up.workspace_id = chosen

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _backfill_workspace_timeline_snapshots() -> None:
    from services.workspace_timeline import backfill_timeline_snapshots

    db = SessionLocal()
    try:
        backfill_timeline_snapshots(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    observability.configure_logging()
    validate_runtime_settings()
    if observability.configure_sentry():
        logger.info("Sentry error tracking enabled for %s", settings.APP_ENV)

    for warning in collect_runtime_setting_errors(
        settings.model_copy(update={"APP_ENV": "production"})
    ):
        if not settings.is_production:
            logger.debug("production readiness: %s", warning)

    if settings.RUN_MIGRATIONS_ON_STARTUP:
        _run_migrations()
    else:
        logger.info("RUN_MIGRATIONS_ON_STARTUP=false; expecting an external migrate step.")

    # Heuristic orphan backfill is unsafe on multi-tenant DBs. Off in production
    # unless explicitly re-enabled.
    allow_orphan_backfill = bool(settings.BACKFILL_ORPHAN_UPLOAD_WORKSPACES)
    if settings.is_production:
        allow_orphan_backfill = False
    if allow_orphan_backfill:
        _backfill_upload_workspace_ids()
    _backfill_workspace_timeline_snapshots()

    logger.info("Storage backend: %s", storage.describe())

    scheduler_task = None
    if settings.INTEGRATION_SCHEDULER_ENABLED:
        from services.integration_scheduler import integration_scheduler_loop

        scheduler_task = asyncio.create_task(
            integration_scheduler_loop(settings.INTEGRATION_SCHEDULER_INTERVAL_SECONDS)
        )

    yield

    from services.upload_worker import shutdown_executor

    shutdown_executor()

    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Snaptix", version="0.1.0", lifespan=lifespan)

observability.install(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(workspaces.router)
app.include_router(uploads.router)
app.include_router(datasets.router)
app.include_router(integrations.router)
app.include_router(analysis.router)
app.include_router(dashboards.router)
app.include_router(chat.router)
app.include_router(relations.router)
app.include_router(summaries.router)
app.include_router(workspace_timeline.router)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> Dict[str, str]:
    """Liveness: the process is up. Does not touch dependencies."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    """Readiness: every dependency this instance needs to serve traffic.

    Returns HTTP 503 when database or storage is unavailable so orchestrators
    stop routing traffic. OpenAI being unset is reported but does not fail
    readiness — the product degrades to heuristics.
    """
    from fastapi.responses import JSONResponse

    checks: Dict[str, str] = {}
    ok = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — the whole point is to report it
        checks["database"] = f"error: {exc}"
        ok = False

    try:
        probe = "healthcheck/.probe"
        storage.write_bytes(probe, b"ok")
        storage.delete(probe)
        checks["storage"] = f"ok ({storage.backend()})"
    except Exception as exc:  # noqa: BLE001
        checks["storage"] = f"error: {exc}"
        ok = False

    from services import llm_client

    checks["openai"] = "configured" if llm_client.is_configured() else "not configured"

    body = {"status": "ready" if ok else "degraded", "checks": checks}
    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body
