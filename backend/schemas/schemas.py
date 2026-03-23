from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    id: str
    filename: str
    status: str
    user_description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetResponse(BaseModel):
    id: str
    upload_id: str
    name: str
    column_schema: Optional[Dict] = Field(None, alias="schema_json")
    data_summary: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class AnalysisResponse(BaseModel):
    id: str
    dataset_id: str
    type: str
    result_json: Optional[Dict]
    ai_summary: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardResponse(BaseModel):
    id: str
    name: str
    layout_json: Optional[Dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    dataset_id: str
    question: str


class ChatResponse(BaseModel):
    answer: str
    chart_data: Optional[Dict] = None


class HealthResponse(BaseModel):
    status: str
