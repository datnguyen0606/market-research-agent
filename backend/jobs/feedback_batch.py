"""
Implicit-feedback batch job.

Two passes over feedback_events, both keyed off the LangSmith run_id captured
at log time:
1. Classify pending chat_sent messages (intent IS NULL) into correction /
   clarifying_question / satisfied / other using a cheap LLM call.
2. Mirror every event with a known run_id — and, for chat_sent, a known
   intent — onto that run as LangSmith feedback, same pattern as judge scores.

Usage: python -m jobs.feedback_batch
"""
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Add backend/ to path so app imports work when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.chat_intent import classify_chat_intent
from app.integrations.langsmith import attach_feedback
from app.db.postgres import (
    init_pool,
    fetch_unclassified_chat_events,
    update_event_intent,
    fetch_unsynced_feedback_events,
    mark_event_synced,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # events per pass, per run

# chat_sent intents map to a numeric score for trend dashboards; "other" stays
# unscored since it doesn't indicate satisfaction either way.
INTENT_SCORES = {"correction": 0.0, "clarifying_question": 0.5, "satisfied": 1.0, "other": None}
EVENT_SCORES = {"regenerated": 0.0, "exported": 1.0}


def _classify_pending_chats() -> None:
    rows = fetch_unclassified_chat_events(limit=BATCH_SIZE)
    if not rows:
        logger.info("No unclassified chat events")
        return

    logger.info("Classifying %d chat events", len(rows))
    for row in rows:
        try:
            result = classify_chat_intent(row["message"])
            update_event_intent(row["id"], result["intent"])
        except Exception:
            logger.exception("Failed to classify event id=%s", row["id"])


def _sync_to_langsmith() -> None:
    rows = fetch_unsynced_feedback_events(limit=BATCH_SIZE)
    if not rows:
        logger.info("No feedback events pending LangSmith sync")
        return

    logger.info("Syncing %d feedback events to LangSmith", len(rows))
    for row in rows:
        try:
            if row["event_type"] == "chat_sent":
                attach_feedback(
                    row["langsmith_run_id"], key="chat_intent",
                    score=INTENT_SCORES.get(row["intent"]), value=row["intent"], comment=row.get("message"),
                )
            else:
                attach_feedback(row["langsmith_run_id"], key=row["event_type"], score=EVENT_SCORES.get(row["event_type"]))
            mark_event_synced(row["id"])
        except Exception:
            logger.exception("Failed to sync event id=%s", row["id"])


def run_batch() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set — aborting")
        sys.exit(1)

    init_pool()
    _classify_pending_chats()
    _sync_to_langsmith()


if __name__ == "__main__":
    run_batch()
