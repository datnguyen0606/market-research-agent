from typing import Any, Optional
from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    company_name: str = Field(..., min_length=1)
    ticker: str = Field(..., min_length=1)
    focus_areas: list[str] = Field(default_factory=list)


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    current_node: Optional[str] = None
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    timestamp: Optional[str] = None
    validation_passed: Optional[bool] = None
    validation_warning: Optional[str] = None
    report_data: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class UploadResponse(BaseModel):
    ticker: str
    r2_key: str
    pages_processed: int
    chunks_stored: int
    status: str = "indexed"


class FeedbackRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    langsmith_trace_id: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^report_regenerated$")
    rating: Optional[int] = None
