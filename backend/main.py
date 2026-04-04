from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from database import Base, SessionLocal, engine
from routes import (
    analysis,
    auth,
    chat,
    dashboards,
    datasets,
    relations,
    summaries,
    uploads,
    workspace_timeline,
    workspaces,
)
from config import settings
from schemas import HealthResponse


def _cors_allow_origins() -> list[str]:
    return [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]


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


def _ensure_dataset_dashboard_plan_column() -> None:
    insp = inspect(engine)
    if not insp.has_table("datasets"):
        return
    cols = {c["name"] for c in insp.get_columns("datasets")}
    if "dashboard_plan_json" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE datasets ADD COLUMN dashboard_plan_json TEXT"))


def _backfill_workspace_timeline_snapshots() -> None:
    from database import SessionLocal
    from services.workspace_timeline import backfill_timeline_snapshots

    db = SessionLocal()
    try:
        backfill_timeline_snapshots(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_dataset_business_classification_column() -> None:
    insp = inspect(engine)
    if not insp.has_table("datasets"):
        return
    cols = {c["name"] for c in insp.get_columns("datasets")}
    if "business_classification" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE datasets ADD COLUMN business_classification VARCHAR"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    _ensure_dataset_dashboard_plan_column()
    _ensure_dataset_business_classification_column()
    _backfill_upload_workspace_ids()
    _backfill_workspace_timeline_snapshots()
    yield


app = FastAPI(title="Excel Consultant", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(uploads.router)
app.include_router(datasets.router)
app.include_router(analysis.router)
app.include_router(dashboards.router)
app.include_router(chat.router)
app.include_router(relations.router)
app.include_router(summaries.router)
app.include_router(workspace_timeline.router)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}
