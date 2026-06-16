import logging
import os

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def init_checkpointer() -> AsyncPostgresSaver:
    global _pool, _checkpointer
    _pool = AsyncConnectionPool(
        conninfo=os.getenv("DATABASE_URL"),
        max_size=10,
        kwargs={"autocommit": True},
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()  # creates checkpoints + checkpoint_writes tables
    logger.info("LangGraph PostgreSQL checkpointer ready")
    return _checkpointer


async def close_checkpointer() -> None:
    global _pool
    if _pool:
        await _pool.close()
        logger.info("Checkpointer pool closed")


def get_checkpointer() -> AsyncPostgresSaver:
    return _checkpointer
