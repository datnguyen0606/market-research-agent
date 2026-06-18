"""
Combined entrypoint for the Railway cron service.

Runs all periodic batch jobs back to back so a single scheduled service covers
everything. Currently runs: feedback_batch (classify chat intents + sync to LangSmith).

Usage: python -m jobs.scheduled
"""
import logging

from jobs import feedback_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Scheduled batch: running feedback_batch")
    feedback_batch.run_batch()


if __name__ == "__main__":
    main()
