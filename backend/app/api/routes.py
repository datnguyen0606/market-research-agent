import asyncio
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
    delete_parent_blocks, insert_parent_blocks, upsert_document,
    insert_report_placeholder, insert_feedback_event, fetch_langsmith_run_id,
)
from app.rag.chunker import extract_pages, chunk_document
from app.rag.embedder import embed_chunks
from app.rag.retriever import delete_ticker_index, upsert_to_qdrant
from app.storage.r2 import upload_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _sse(data: dict) -> dict:
    return {"data": json.dumps(data)}


def _initial_state(ticker: str, company_name: str, focus_areas: list[str]) -> dict:
    return {
        "company_name": company_name,
        "ticker": ticker,
        "raw_query": f"Financial analysis of {company_name} ({ticker})",
        "focus_areas": focus_areas,
        "retrieved_financials": [],
        "market_news": [],
        "financial_analysis": {},
        "messages": [],
        "critic_feedback": None,
        "iterations": 0,
        "is_approved": False,
        "final_report_json": None,
    }


@router.get("/research/stream")
async def stream_report(
    request: Request,
    ticker: str,
    company_name: str,
    focus_areas: str = "",
    thread_id: str | None = None,
):
    tid = thread_id or str(uuid.uuid4())
    langsmith_run_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": tid},
        "run_id": langsmith_run_id,
        "metadata": {"thread_id": tid, "ticker": ticker.upper()},
    }
    checkpointer = request.app.state.checkpointer
    graph = build_graph(checkpointer)
    ticker = ticker.upper()

    # Reconnect: thread already completed
    existing = await graph.aget_state(config)
    if existing.values and existing.values.get("final_report_json"):
        async def _immediate():
            state = existing.values
            yield _sse({
                "event": "done",
                "thread_id": tid,
                "ticker": ticker,
                "company_name": company_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "validation_passed": state.get("is_approved", False),
                "validation_warning": (
                    "Report delivered after 3 validation attempts without full approval. "
                    "Financial figures should be independently verified."
                ) if not state.get("is_approved") else None,
                "report_data": state["final_report_json"],
            })
        return EventSourceResponse(_immediate())

    initial = _initial_state(
        ticker=ticker,
        company_name=company_name,
        focus_areas=[f.strip() for f in focus_areas.split(",") if f.strip()],
    )

    async def generator():
        try:
            async for chunk in graph.astream(initial, config, stream_mode="updates"):
                for node_name in chunk:
                    yield _sse({"event": "node_complete", "node": node_name})

            final = (await graph.aget_state(config)).values
            report = final.get("final_report_json") or {}
            validation_passed = final.get("is_approved", False)
            critic_iterations = report.get("critic_iterations", 0)

            # Register unscored row — batch job will fill in judge scores later
            await asyncio.to_thread(
                insert_report_placeholder, tid, ticker, critic_iterations, langsmith_run_id
            )

            yield _sse({
                "event": "done",
                "thread_id": tid,
                "ticker": ticker,
                "company_name": company_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "validation_passed": validation_passed,
                "validation_warning": (
                    "Report delivered after 3 validation attempts without full approval. "
                    "Financial figures should be independently verified."
                ) if not validation_passed else None,
                "report_data": report,
            })

        except ValueError as exc:
            yield _sse({"event": "error", "message": str(exc)})
        except Exception:
            logger.exception("Stream error thread=%s", tid)
            yield _sse({"event": "error", "message": "An unexpected error occurred. Please try again."})

    return EventSourceResponse(generator())


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

    # Raw signal — classified into an intent (correction/question/satisfied) by the
    # feedback batch job, then mirrored to this run in LangSmith.
    await asyncio.to_thread(
        insert_feedback_event, thread_id, existing.values.get("ticker"), "chat_sent",
        body.message, langsmith_run_id,
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
                "validation_passed": final.get("is_approved", False),
                "report_data": final.get("final_report_json") or {},
            })

        except Exception:
            logger.exception("Chat error thread=%s", thread_id)
            yield _sse({"event": "error", "message": "Chat failed. Please try again."})

    return EventSourceResponse(generator())


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(ticker: str = Form(...), file: UploadFile = File(...)):
    ticker = ticker.upper()
    pdf_bytes = await file.read()

    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit.")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count == 0:
            raise ValueError("PDF has no pages.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Not a valid PDF or contains no extractable text.") from exc

    filename = file.filename or f"{ticker}.pdf"
    r2_key = upload_pdf(ticker, filename, pdf_bytes)
    pages = extract_pages(doc)
    chunks = chunk_document(pages)

    child_chunks = [c for c in chunks if c["type"] == "child"]
    if not child_chunks:
        raise HTTPException(status_code=400, detail="PDF contains no extractable text content.")

    embeddings = embed_chunks([c["text"] for c in child_chunks])

    delete_ticker_index(ticker)
    delete_parent_blocks(ticker)
    upsert_to_qdrant(ticker, chunks, embeddings, r2_key)
    insert_parent_blocks(ticker, chunks, r2_key)
    upsert_document(ticker, r2_key, filename, len(pages), len(child_chunks))

    logger.info("Indexed %d chunks for ticker=%s", len(child_chunks), ticker)
    return UploadResponse(
        ticker=ticker,
        r2_key=r2_key,
        pages_processed=len(pages),
        chunks_stored=len(child_chunks),
    )


@router.post("/events")
async def log_event(payload: EventRequest):
    """Log an implicit, behavior-based signal (regenerated/exported) against the
    report's existing LangSmith run — mirrored there by the feedback batch job."""
    langsmith_run_id = await asyncio.to_thread(fetch_langsmith_run_id, payload.thread_id)
    await asyncio.to_thread(
        insert_feedback_event, payload.thread_id, payload.ticker, payload.event_type, None, langsmith_run_id
    )
    return {"logged": True}
