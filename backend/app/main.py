import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# LangSmith tracing — set before any LangChain imports
if os.getenv("LANGCHAIN_TRACING_V2"):
    os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "false")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "market-research-agent")
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Market Research Agent starting up")
    yield
    logger.info("Market Research Agent shutting down")


app = FastAPI(title="Market Research Agent API", version="1.0.0", lifespan=lifespan)

allowed_origins = [
    os.getenv("FRONTEND_URL", "https://your-app.vercel.app"),
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
