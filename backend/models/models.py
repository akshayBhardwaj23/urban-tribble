from __future__ import annotations

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    image = Column(String, nullable=True)
    active_workspace_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UploadStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_url = Column(String, nullable=False)
    user_description = Column(Text, nullable=True)
    status = Column(Enum(UploadStatus), default=UploadStatus.pending, nullable=False)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    upload_id = Column(String, ForeignKey("uploads.id"), nullable=False)
    name = Column(String, nullable=False)
    schema_json = Column(Text, nullable=True)
    data_summary = Column(Text, nullable=True)
    cleaned_report_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    type = Column(String, nullable=False)
    result_json = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Dashboard(Base):
    __tablename__ = "dashboards"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    name = Column(String, nullable=False)
    layout_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DatasetRelation(Base):
    __tablename__ = "dataset_relations"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    source_dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    target_dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    source_column = Column(String, nullable=False)
    target_column = Column(String, nullable=False)
    relation_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
