import asyncio
import io
import json
import logging
import uuid
from datetime import datetime, timezone

import fitz
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage

from app.schemas import UploadResponse, EventRequest, ChatMessage
from app.agents.graph import build_graph
from app.db.postgres import (
    insert_document, insert_parent_blocks, insert_feedback_event,
)
from app.rag.chunker import extract_pages, chunk_document, extract_docx_pages, chunk_docx_pages
from app.rag.embedder import embed_chunks, embed_sparse
from app.rag.retriever import upsert_to_qdrant
from app.storage.r2 import upload_document as r2_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
ACCEPTED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _sse(data: dict) -> dict:
    return {"data": json.dumps(data)}


def _initial_state(query: str) -> dict:
    return {
        "query": query,
        "search_queries": [],
        "retrieved_docs": [],
        "web_results": [],
        "messages": [],
        "answer": None,
        "sources": [],
        "grounding_passed": False,
    }


@router.get("/research/stream")
async def stream_research(
    request: Request,
    query: str,
    thread_id: str | None = None,
):
    tid = thread_id or str(uuid.uuid4())
    langsmith_run_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": tid},
        "run_id": langsmith_run_id,
        "metadata": {"thread_id": tid},
    }
    checkpointer = request.app.state.checkpointer
    graph = build_graph(checkpointer)

    # Reconnect: thread already has an answer
    existing = await graph.aget_state(config)
    if existing.values and existing.values.get("answer"):
        async def _immediate():
            state = existing.values
            yield _sse({
                "event": "done",
                "thread_id": tid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "answer": state["answer"],
                "sources": state.get("sources", []),
                "grounding_passed": state.get("grounding_passed", True),
            })
        return EventSourceResponse(_immediate(), ping=15)

    initial = _initial_state(query=query)

    async def generator():
        try:
            async for chunk in graph.astream(initial, config, stream_mode="updates"):
                for node_name in chunk:
                    yield _sse({"event": "node_complete", "node": node_name})

            final = (await graph.aget_state(config)).values
            yield _sse({
                "event": "done",
                "thread_id": tid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "answer": final.get("answer", ""),
                "sources": final.get("sources", []),
                "grounding_passed": final.get("grounding_passed", True),
            })

        except ValueError as exc:
            yield _sse({"event": "error", "message": str(exc)})
        except Exception:
            logger.exception("Stream error thread=%s", tid)
            yield _sse({"event": "error", "message": "An unexpected error occurred. Please try again."})

    return EventSourceResponse(generator(), ping=15)


@router.post("/research/chat/{thread_id}")
async def chat_stream(request: Request, thread_id: str, body: ChatMessage):
    langsmith_run_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "run_id": langsmith_run_id,
        "metadata": {"thread_id": thread_id, "chat": True},
    }
    checkpointer = request.app.state.checkpointer
    graph = build_graph(checkpointer)

    existing = await graph.aget_state(config)
    if not existing.values:
        raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found.")

    await asyncio.to_thread(
        insert_feedback_event, thread_id, "chat_sent", body.message, langsmith_run_id,
    )

    async def generator():
        try:
            async for chunk in graph.astream(
                {"messages": [HumanMessage(content=body.message)]},
                config,
                stream_mode="updates",
            ):
                for node_name in chunk:
                    yield _sse({"event": "node_complete", "node": node_name})

            final = (await graph.aget_state(config)).values
            yield _sse({
                "event": "done",
                "thread_id": thread_id,
                "answer": final.get("answer", ""),
                "sources": final.get("sources", []),
                "grounding_passed": final.get("grounding_passed", True),
            })

        except Exception:
            logger.exception("Chat error thread=%s", thread_id)
            yield _sse({"event": "error", "message": "Chat failed. Please try again."})

    return EventSourceResponse(generator(), ping=15)


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit.")

    filename = file.filename or "document"
    content_type = file.content_type or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Determine file type
    if content_type in ACCEPTED_TYPES:
        file_type = ACCEPTED_TYPES[content_type]
    elif ext == "pdf":
        file_type = "pdf"
    elif ext == "docx":
        file_type = "docx"
    else:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

    doc_id = str(uuid.uuid4())

    # Parse and chunk
    prefix = doc_id[:12] + "_"
    if file_type == "pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if doc.page_count == 0:
                raise ValueError("PDF has no pages.")
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Not a valid PDF or contains no extractable text.") from exc
        raw_pages = extract_pages(doc)
        page_count = len(raw_pages)
        chunks = [
            {**chunk, "id": prefix + chunk["id"], "parent_id": prefix + chunk["parent_id"]}
            for chunk in chunk_document(raw_pages)
        ]
    else:
        raw_pages = extract_docx_pages(file_bytes)
        page_count = len(raw_pages)
        chunks = [
            {**chunk, "id": prefix + chunk["id"], "parent_id": prefix + chunk["parent_id"]}
            for chunk in chunk_docx_pages(raw_pages)
        ]

    child_chunks = [c for c in chunks if c["type"] == "child"]
    if not child_chunks:
        raise HTTPException(status_code=400, detail="Document contains no extractable text.")

    # Embed (dense + sparse)
    texts = [c["text"] for c in child_chunks]
    dense_embeddings = embed_chunks(texts)
    sparse_embeddings = embed_sparse(texts)

    # Store in R2
    r2_key = r2_upload(doc_id, filename, file_bytes)

    # Upsert to Qdrant
    upsert_to_qdrant(doc_id, chunks, dense_embeddings, sparse_embeddings, r2_key, filename)

    # Store parent blocks + document record in Postgres
    await asyncio.to_thread(insert_parent_blocks, doc_id, chunks, r2_key, filename)
    await asyncio.to_thread(insert_document, doc_id, filename, file_type, r2_key, page_count, len(child_chunks))

    logger.info("Indexed %d chunks for doc_id=%s filename=%s", len(child_chunks), doc_id, filename)
    return UploadResponse(
        doc_id=doc_id,
        filename=filename,
        file_type=file_type,
        pages_processed=page_count,
        chunks_stored=len(child_chunks),
    )


@router.post("/events")
async def log_event(payload: EventRequest):
    await asyncio.to_thread(insert_feedback_event, payload.thread_id, payload.event_type)
    return {"logged": True}
