from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from deps import require_active_workspace
from models.models import ChatMessage, Dataset, Upload, User
from services.workspace_query import (
    dataset_upload_pairs_for_workspace,
    get_dataset_upload_in_workspace,
)
from services.query_engine import QueryEngine

router = APIRouter(prefix="/api/chat", tags=["chat"])

query_engine = QueryEngine()


class ChatRequest(BaseModel):
    dataset_id: str
    question: str


class WorkspaceChatRequest(BaseModel):
    question: str


@router.post("/")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    row = get_dataset_upload_in_workspace(db, req.dataset_id, workspace_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    dataset, upload = row

    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")

    df = pd.read_parquet(str(parquet_path))
    schema = json.loads(dataset.schema_json) if dataset.schema_json else {}

    db.add(ChatMessage(
        dataset_id=dataset.id,
        role="user",
        content=req.question,
    ))

    result = query_engine.ask(
        question=req.question,
        df=df,
        schema=schema,
        user_description=upload.user_description,
    )

    answer = result.get("answer", "I couldn't process that question.")
    chart_data = result.get("chart_data")

    db.add(ChatMessage(
        dataset_id=dataset.id,
        role="assistant",
        content=answer,
    ))
    db.commit()

    return {
        "answer": answer,
        "chart_data": chart_data,
    }


@router.post("/workspace")
def workspace_chat(
    req: WorkspaceChatRequest,
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Chat across all datasets in the workspace."""
    _, workspace_id = ws
    all_pairs = dataset_upload_pairs_for_workspace(db, workspace_id).all()

    if not all_pairs:
        raise HTTPException(404, "No datasets found in workspace")

    dataframes = []
    for ds, up in all_pairs:
        parquet_path = Path(up.file_url).parent / f"{up.id}_cleaned.parquet"
        if not parquet_path.exists():
            continue
        df = pd.read_parquet(str(parquet_path))
        schema = json.loads(ds.schema_json) if ds.schema_json else {}
        dataframes.append((ds.name, df, schema, up.user_description))

    if not dataframes:
        raise HTTPException(404, "No cleaned data files found")

    result = query_engine.ask_multi(
        question=req.question,
        dataframes=dataframes,
    )

    answer = result.get("answer", "I couldn't process that question.")
    chart_data = result.get("chart_data")

    first_ds = all_pairs[0][0]
    db.add(ChatMessage(
        dataset_id=first_ds.id,
        role="user",
        content=f"[All Datasets] {req.question}",
    ))
    db.add(ChatMessage(
        dataset_id=first_ds.id,
        role="assistant",
        content=answer,
    ))
    db.commit()

    return {
        "answer": answer,
        "chart_data": chart_data,
    }


@router.get("/history/{dataset_id}")
def get_chat_history(dataset_id: str, db: Session = Depends(get_db)):
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.dataset_id == dataset_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
        }
        for msg in messages
    ]
