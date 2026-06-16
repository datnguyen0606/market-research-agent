import json
import logging
import os

import redis as redis_lib

logger = logging.getLogger(__name__)

_client: redis_lib.Redis | None = None

TASK_TTL = 86_400    # 24 h — completed reports survive overnight
ACTIVE_JOB_TTL = 600  # 10 min — auto-expires stale in-progress locks


def init_redis() -> None:
    global _client
    _client = redis_lib.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        decode_responses=True,
    )
    _client.ping()
    logger.info("Redis connection initialized")


def _r() -> redis_lib.Redis:
    return _client


# ── Task store ─────────────────────────────────────────────────────────────────

def get_task(task_id: str) -> dict | None:
    data = _r().get(f"task:{task_id}")
    return json.loads(data) if data else None


def set_task(task_id: str, data: dict) -> None:
    _r().setex(f"task:{task_id}", TASK_TTL, json.dumps(data))


def update_task_field(task_id: str, **fields) -> None:
    data = get_task(task_id) or {}
    data.update(fields)
    set_task(task_id, data)


# ── Active-job deduplication ───────────────────────────────────────────────────

def get_active_job(ticker: str) -> str | None:
    return _r().get(f"active:{ticker}")


def set_active_job(ticker: str, task_id: str) -> None:
    _r().setex(f"active:{ticker}", ACTIVE_JOB_TTL, task_id)


def delete_active_job(ticker: str) -> None:
    _r().delete(f"active:{ticker}")
