import logging
import os

logger = logging.getLogger(__name__)


def attach_feedback(
    run_id: str | None,
    key: str,
    score: float | None = None,
    value: str | None = None,
    comment: str | None = None,
) -> bool:
    """
    Attach a named feedback entry to a LangSmith run. No-ops quietly if tracing
    isn't configured or run_id is unknown; swallows API errors since this is a
    best-effort mirror — PostgreSQL is always the durable system of record.
    """
    if not run_id or not os.getenv("LANGCHAIN_API_KEY"):
        return False
    try:
        from langsmith import Client
        Client().create_feedback(run_id=run_id, key=key, score=score, value=value, comment=comment)
        return True
    except Exception:
        logger.warning("LangSmith feedback failed run=%s key=%s", run_id, key, exc_info=True)
        return False
