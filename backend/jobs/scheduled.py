"""
Combined entrypoint for the Railway cron service — runs every periodic batch job
back to back so a single scheduled service covers all of them.

Usage: python -m jobs.scheduled
"""
import logging

from jobs import judge_batch, feedback_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Scheduled batch: running judge_batch")
    judge_batch.run_batch()
    logger.info("Scheduled batch: running feedback_batch")
    feedback_batch.run_batch()


if __name__ == "__main__":
    main()
