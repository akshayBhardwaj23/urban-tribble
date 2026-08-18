from datetime import datetime

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    id: str
    filename: str
    status: str
    user_description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetResponse(BaseModel):
    id: str
    upload_id: str
    name: str
    column_schema: dict | None = Field(None, alias="schema_json")
    data_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class AnalysisResponse(BaseModel):
    id: str
    dataset_id: str
    type: str
    result_json: dict | None
    ai_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardResponse(BaseModel):
    id: str
    name: str
    layout_json: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    dataset_id: str
    question: str


class ChatResponse(BaseModel):
    answer: str
    chart_data: dict | None = None


class HealthResponse(BaseModel):
    status: str
