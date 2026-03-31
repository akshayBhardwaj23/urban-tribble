from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from deps import require_active_workspace
from models.models import ChatMessage, Upload, User
from services.workspace_query import (
    dataset_upload_pairs_for_workspace,
    get_dataset_upload_in_workspace,
)
from services.query_engine import QueryEngine

router = APIRouter(prefix="/api/chat", tags=["chat"])

query_engine = QueryEngine()

# Workspace-scoped chat stores user text with this prefix on the anchor dataset row.
CHAT_WORKSPACE_USER_PREFIX = "[All Datasets] "
MAX_CHAT_HISTORY_PAIRS = 12


def _prior_chat_pairs(
    messages: List[ChatMessage],
    *,
    workspace_scope: bool,
) -> List[Tuple[str, str]]:
    """Well-formed (user, assistant) turns, optionally filtered by workspace vs single-dataset."""
    pairs: List[Tuple[str, str]] = []
    i = 0
    while i + 1 < len(messages):
        u, a = messages[i], messages[i + 1]
        if u.role != "user" or a.role != "assistant":
            i += 1
            continue
        uc = u.content
        is_ws = uc.startswith(CHAT_WORKSPACE_USER_PREFIX)
        if workspace_scope:
            if not is_ws:
                i += 2
                continue
            uq = uc[len(CHAT_WORKSPACE_USER_PREFIX) :].strip() or uc
        else:
            if is_ws:
                i += 2
                continue
            uq = uc
        pairs.append((uq, a.content))
        i += 2
    if len(pairs) > MAX_CHAT_HISTORY_PAIRS:
        pairs = pairs[-MAX_CHAT_HISTORY_PAIRS :]
    return pairs


def _messages_for_history_response(
    rows: List[ChatMessage],
    *,
    workspace_scope: bool,
) -> List[dict]:
    out: List[dict] = []
    i = 0
    while i + 1 < len(rows):
        u, a = rows[i], rows[i + 1]
        if u.role != "user" or a.role != "assistant":
            i += 1
            continue
        is_ws = u.content.startswith(CHAT_WORKSPACE_USER_PREFIX)
        if workspace_scope:
            if not is_ws:
                i += 2
                continue
        else:
            if is_ws:
                i += 2
                continue
        display_user = u.content
        if workspace_scope and display_user.startswith(CHAT_WORKSPACE_USER_PREFIX):
            display_user = display_user[len(CHAT_WORKSPACE_USER_PREFIX) :].strip() or u.content
        out.append(
            {
                "id": u.id,
                "role": u.role,
                "content": display_user,
                "created_at": u.created_at.isoformat(),
            }
        )
        out.append(
            {
                "id": a.id,
                "role": a.role,
                "content": a.content,
                "created_at": a.created_at.isoformat(),
            }
        )
        i += 2
    return out


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

    prior_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.dataset_id == dataset.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history = _prior_chat_pairs(prior_rows, workspace_scope=False)

    result = query_engine.ask(
        question=req.question,
        df=df,
        schema=schema,
        user_description=upload.user_description,
        history=history,
    )

    answer = result.get("answer", "I couldn't process that question.")
    chart_data = result.get("chart_data")

    db.add(
        ChatMessage(
            dataset_id=dataset.id,
            role="user",
            content=req.question,
        )
    )
    db.add(
        ChatMessage(
            dataset_id=dataset.id,
            role="assistant",
            content=answer,
        )
    )
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

    first_ds = all_pairs[0][0]
    prior_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.dataset_id == first_ds.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history = _prior_chat_pairs(prior_rows, workspace_scope=True)

    result = query_engine.ask_multi(
        question=req.question,
        dataframes=dataframes,
        history=history,
    )

    answer = result.get("answer", "I couldn't process that question.")
    chart_data = result.get("chart_data")

    db.add(
        ChatMessage(
            dataset_id=first_ds.id,
            role="user",
            content=f"{CHAT_WORKSPACE_USER_PREFIX}{req.question}",
        )
    )
    db.add(
        ChatMessage(
            dataset_id=first_ds.id,
            role="assistant",
            content=answer,
        )
    )
    db.commit()

    return {
        "answer": answer,
        "chart_data": chart_data,
    }


@router.get("/history/{dataset_id}")
def get_chat_history(
    dataset_id: str,
    workspace: bool = Query(False, description="If true, return only workspace (all-sources) thread"),
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    _, workspace_id = ws
    if not get_dataset_upload_in_workspace(db, dataset_id, workspace_id):
        raise HTTPException(404, "Dataset not found")

    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.dataset_id == dataset_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return _messages_for_history_response(rows, workspace_scope=workspace)
