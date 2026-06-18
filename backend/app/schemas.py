from typing import Optional
from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    pages_processed: int
    chunks_stored: int
    status: str = "indexed"


class EventRequest(BaseModel):
    """chat_sent is logged server-side; this endpoint carries client-only signals."""
    thread_id: str = Field(..., min_length=1)
    event_type: str = Field(..., pattern="^(regenerated|exported)$")


class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1)
