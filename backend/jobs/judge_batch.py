"""
LLM-as-Judge batch scoring job.

Queries PostgreSQL for delivered reports that have not yet been scored,
runs the judge (claude-opus-4-8) on each, writes scores back, and attaches
feedback to the corresponding LangSmith run.

Railway schedule: run every 6 hours (cron: 0 */6 * * *)
Usage: python -m jobs.judge_batch
"""
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Add backend/ to path so app imports work when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from app.agents.judge import run_judge
from app.db.postgres import init_pool, fetch_unscored_reports, update_report_scores
from app.integrations.langsmith import attach_feedback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # reports per run


def _load_checkpoint_state(conn_string: str, thread_id: str) -> dict:
    """Load the final LangGraph state for a completed thread."""
    with psycopg.connect(conn_string) as conn:
        checkpointer = PostgresSaver(conn)
        checkpoint = checkpointer.get({"configurable": {"thread_id": thread_id}})
        if checkpoint:
            return checkpoint.get("channel_values", {})
    return {}


def _attach_langsmith(run_id: str | None, judge: dict) -> None:
    if attach_feedback(run_id, key="overall_quality", score=judge.get("overall"), comment=judge.get("feedback")):
        for dim, score in (judge.get("scores") or {}).items():
            attach_feedback(run_id, key=dim, score=score)
        logger.info("LangSmith feedback attached run=%s", run_id)


def run_batch() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set — aborting")
        sys.exit(1)

    init_pool()
    rows = fetch_unscored_reports(limit=BATCH_SIZE)

    if not rows:
        logger.info("No unscored reports — nothing to do")
        return

    logger.info("Scoring %d reports", len(rows))
    succeeded = failed = 0

    for row in rows:
        thread_id = row["thread_id"]
        ticker = row["ticker"]
        langsmith_run_id = row.get("langsmith_run_id")

        try:
            state = _load_checkpoint_state(database_url, thread_id)
            if not state:
                logger.warning("No checkpoint for thread=%s — skipping", thread_id)
                failed += 1
                continue

            report = state.get("final_report_json")
            if not report:
                logger.warning("No final report in checkpoint thread=%s — skipping", thread_id)
                failed += 1
                continue

            judge = run_judge(
                ticker=ticker,
                retrieved_financials=state.get("retrieved_financials") or [],
                market_news=state.get("market_news") or [],
                report=report,
            )

            update_report_scores(thread_id, judge, langsmith_run_id)
            _attach_langsmith(langsmith_run_id, judge)

            logger.info("Scored thread=%s ticker=%s overall=%.2f passed=%s",
                        thread_id, ticker, judge.get("overall", 0), judge.get("passed"))
            succeeded += 1

        except Exception:
            logger.exception("Failed to score thread=%s", thread_id)
            failed += 1

    logger.info("Batch complete — succeeded=%d failed=%d", succeeded, failed)


if __name__ == "__main__":
    run_batch()
