from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from database import Base, engine
from routes import analysis, auth, chat, dashboards, datasets, relations, uploads, workspaces
from schemas import HealthResponse


def _ensure_dataset_dashboard_plan_column() -> None:
    insp = inspect(engine)
    if not insp.has_table("datasets"):
        return
    cols = {c["name"] for c in insp.get_columns("datasets")}
    if "dashboard_plan_json" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE datasets ADD COLUMN dashboard_plan_json TEXT"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    _ensure_dataset_dashboard_plan_column()
    yield


app = FastAPI(title="Excel Consultant", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/health", response_model=HealthResponse)
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}
