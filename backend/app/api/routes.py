import logging
import uuid
from datetime import datetime, timezone

import fitz
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.schemas import ReportRequest, TaskStatusResponse, UploadResponse, FeedbackRequest
from app.agents.graph import task_store, active_jobs, run_graph
from app.rag.chunker import extract_pages, chunk_document
from app.rag.embedder import embed_chunks
from app.rag.retriever import delete_ticker_index, upsert_to_qdrant
from app.storage.r2 import upload_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/research/generate", status_code=202)
async def generate_report(payload: ReportRequest, background_tasks: BackgroundTasks):
    ticker = payload.ticker.upper()

    # FR-016: return existing in-progress job
    if ticker in active_jobs:
        existing_id = active_jobs[ticker]
        existing = task_store.get(existing_id, {})
        return JSONResponse(
            status_code=200,
            content={
                "task_id": existing_id,
                "status": existing.get("status", "processing"),
                "current_node": existing.get("current_node"),
            },
        )

    task_id = f"job_{uuid.uuid4().hex[:12]}"
    task_store[task_id] = {
        "status": "processing",
        "current_node": "router",
        "company_name": payload.company_name,
        "ticker": ticker,
    }
    active_jobs[ticker] = task_id
    payload.ticker = ticker
    background_tasks.add_task(run_graph, task_id, payload)

    return {"task_id": task_id, "status": "processing", "current_node": "router"}


@router.get("/research/report/{task_id}")
async def get_report(task_id: str):
    job = task_store.get(task_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    if job["status"] == "processing":
        return {"task_id": task_id, "status": "processing", "current_node": job.get("current_node")}

    if job["status"] == "failed":
        return {"task_id": task_id, "status": "failed", "error_message": job.get("error_message")}

    response: dict = {
        "task_id": task_id,
        "status": "completed",
        "company_name": job.get("company_name"),
        "ticker": job.get("ticker"),
        "timestamp": job.get("timestamp"),
        "validation_passed": job.get("validation_passed", True),
        "report_data": job.get("report_data"),
    }
    if job.get("validation_warning"):
        response["validation_warning"] = job["validation_warning"]
    return response


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

    r2_key = upload_pdf(ticker, file.filename or f"{ticker}.pdf", pdf_bytes)
    pages = extract_pages(doc)
    chunks = chunk_document(pages)

    child_chunks = [c for c in chunks if c["type"] == "child"]
    if not child_chunks:
        raise HTTPException(status_code=400, detail="PDF contains no extractable text content.")

    child_texts = [c["text"] for c in child_chunks]
    embeddings = embed_chunks(child_texts)

    delete_ticker_index(ticker)
    upsert_to_qdrant(ticker, chunks, embeddings, r2_key)

    logger.info("Indexed %d chunks for ticker=%s", len(child_chunks), ticker)
    return UploadResponse(
        ticker=ticker,
        r2_key=r2_key,
        pages_processed=len(pages),
        chunks_stored=len(child_chunks),
    )


@router.post("/feedback")
async def receive_feedback(payload: FeedbackRequest):
    logger.info(
        "Feedback received: task_id=%s action=%s trace=%s",
        payload.task_id,
        payload.action,
        payload.langsmith_trace_id,
    )
    return {"received": True}
