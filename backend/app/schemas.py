from typing import Any, Optional
from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    ticker: str
    r2_key: str
    pages_processed: int
    chunks_stored: int
    status: str = "indexed"


class EventRequest(BaseModel):
    """chat_sent is logged server-side (chat_stream already has the message and
    run_id) — this endpoint only carries client-only signals."""
    thread_id: str = Field(..., min_length=1)
    ticker: Optional[str] = None
    event_type: str = Field(..., pattern="^(regenerated|exported)$")


class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1)
