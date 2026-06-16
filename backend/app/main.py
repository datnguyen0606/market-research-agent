import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

if os.getenv("LANGCHAIN_TRACING_V2"):
    os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "false")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "market-research-agent")
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.db.postgres import init_pool, init_schema
from app.db.checkpointer import init_checkpointer, close_checkpointer
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sync pool (psycopg2) for documents + parent_blocks tables
    init_pool()
    init_schema()
    # Async pool (psycopg3) for LangGraph checkpoints
    app.state.checkpointer = await init_checkpointer()
    logger.info("Market Research Agent ready")
    yield
    await close_checkpointer()
    logger.info("Market Research Agent shut down")


app = FastAPI(title="Market Research Agent API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "https://your-app.vercel.app"),
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
