import os
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=os.getenv("DATABASE_URL"),
    )
    logger.info("PostgreSQL connection pool initialized")


@contextmanager
def get_conn():
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def init_schema() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id          SERIAL PRIMARY KEY,
                    ticker      VARCHAR(20)  NOT NULL,
                    r2_key      TEXT         NOT NULL,
                    filename    TEXT,
                    pages_processed INT,
                    chunks_stored   INT,
                    uploaded_at TIMESTAMPTZ  DEFAULT NOW()
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_ticker
                ON documents(ticker);

                CREATE TABLE IF NOT EXISTS parent_blocks (
                    parent_id   TEXT         NOT NULL,
                    ticker      VARCHAR(20)  NOT NULL,
                    full_text   TEXT         NOT NULL,
                    page        INT,
                    r2_key      TEXT,
                    PRIMARY KEY (parent_id, ticker)
                );

                CREATE INDEX IF NOT EXISTS idx_parent_blocks_ticker
                ON parent_blocks(ticker);

                CREATE TABLE IF NOT EXISTS report_quality (
                    thread_id           TEXT PRIMARY KEY,
                    ticker              VARCHAR(20),
                    langsmith_run_id    TEXT,
                    overall             FLOAT,
                    factual_accuracy    FLOAT,
                    logical_consistency FLOAT,
                    completeness        FLOAT,
                    sentiment_alignment FLOAT,
                    judge_passed        BOOLEAN,
                    critic_iterations   INT,
                    created_at          TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_report_quality_ticker
                ON report_quality(ticker);
                CREATE INDEX IF NOT EXISTS idx_report_quality_created_at
                ON report_quality(created_at);

                CREATE TABLE IF NOT EXISTS feedback_events (
                    id                SERIAL PRIMARY KEY,
                    thread_id         TEXT         NOT NULL,
                    ticker            VARCHAR(20),
                    event_type        VARCHAR(20)  NOT NULL,
                    message           TEXT,
                    intent            VARCHAR(20),
                    langsmith_run_id  TEXT,
                    langsmith_synced  BOOLEAN      DEFAULT FALSE,
                    created_at        TIMESTAMPTZ  DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_feedback_events_thread
                ON feedback_events(thread_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_events_unclassified
                ON feedback_events(created_at)
                WHERE event_type = 'chat_sent' AND intent IS NULL;
                CREATE INDEX IF NOT EXISTS idx_feedback_events_unsynced
                ON feedback_events(created_at)
                WHERE langsmith_synced = FALSE AND langsmith_run_id IS NOT NULL;
            """)
    logger.info("PostgreSQL schema ready")


# ── Document metadata ──────────────────────────────────────────────────────────

def upsert_document(ticker: str, r2_key: str, filename: str, pages: int, chunks: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documents (ticker, r2_key, filename, pages_processed, chunks_stored)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE
                    SET r2_key          = EXCLUDED.r2_key,
                        filename        = EXCLUDED.filename,
                        pages_processed = EXCLUDED.pages_processed,
                        chunks_stored   = EXCLUDED.chunks_stored,
                        uploaded_at     = NOW()
            """, (ticker, r2_key, filename, pages, chunks))


# ── Parent blocks ──────────────────────────────────────────────────────────────

def delete_parent_blocks(ticker: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM parent_blocks WHERE ticker = %s", (ticker,))


def insert_parent_blocks(ticker: str, chunks: list[dict], r2_key: str) -> None:
    parents = [c for c in chunks if c["type"] == "parent"]
    if not parents:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            for block in parents:
                cur.execute("""
                    INSERT INTO parent_blocks (parent_id, ticker, full_text, page, r2_key)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (parent_id, ticker) DO UPDATE
                        SET full_text = EXCLUDED.full_text,
                            page      = EXCLUDED.page,
                            r2_key    = EXCLUDED.r2_key
                """, (block["id"], ticker, block["text"], block["page"], r2_key))


# ── Report quality (LLM-as-Judge scores) ──────────────────────────────────────

def insert_report_placeholder(
    thread_id: str,
    ticker: str,
    critic_iterations: int,
    langsmith_run_id: str | None = None,
) -> None:
    """Insert an unscored row on report delivery. Batch job fills in scores later."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO report_quality (thread_id, ticker, critic_iterations, langsmith_run_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (thread_id) DO NOTHING
            """, (thread_id, ticker, critic_iterations, langsmith_run_id))


def update_report_scores(
    thread_id: str,
    judge_scores: dict,
    langsmith_run_id: str | None = None,
) -> None:
    """Write judge scores into an existing placeholder row. Called by the batch job."""
    s = judge_scores.get("scores") or {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE report_quality
                SET overall             = %s,
                    factual_accuracy    = %s,
                    logical_consistency = %s,
                    completeness        = %s,
                    sentiment_alignment = %s,
                    judge_passed        = %s,
                    langsmith_run_id    = COALESCE(%s, langsmith_run_id)
                WHERE thread_id = %s
            """, (
                judge_scores.get("overall"),
                s.get("factual_accuracy"),
                s.get("logical_consistency"),
                s.get("completeness"),
                s.get("sentiment_alignment"),
                judge_scores.get("passed"),
                langsmith_run_id,
                thread_id,
            ))


def fetch_unscored_reports(limit: int = 50) -> list[dict]:
    """Return rows that have been delivered but not yet judged. Used by the batch job."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT thread_id, ticker, langsmith_run_id, critic_iterations
                FROM report_quality
                WHERE overall IS NULL
                ORDER BY created_at
                LIMIT %s
            """, (limit,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Feedback events (implicit, behavior-based) ────────────────────────────────

def insert_feedback_event(
    thread_id: str,
    ticker: str | None,
    event_type: str,
    message: str | None = None,
    langsmith_run_id: str | None = None,
) -> None:
    """Log a raw behavioral signal (regenerated/exported/chat_sent). Intent for
    chat_sent rows is filled in later by the feedback batch job, which also
    mirrors every row with a known run_id to LangSmith."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO feedback_events (thread_id, ticker, event_type, message, langsmith_run_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (thread_id, ticker, event_type, message, langsmith_run_id))


def fetch_langsmith_run_id(thread_id: str) -> str | None:
    """Look up the report-generation run_id for a thread, so regenerated/exported
    events (which have no run of their own) can be attached to it."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT langsmith_run_id FROM report_quality WHERE thread_id = %s", (thread_id,))
            row = cur.fetchone()
            return row[0] if row else None


def fetch_unclassified_chat_events(limit: int = 100) -> list[dict]:
    """Return chat_sent events with no intent yet. Used by the feedback batch job."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, thread_id, message
                FROM feedback_events
                WHERE event_type = 'chat_sent' AND intent IS NULL
                ORDER BY created_at
                LIMIT %s
            """, (limit,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def update_event_intent(event_id: int, intent: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE feedback_events SET intent = %s WHERE id = %s", (intent, event_id))


def fetch_unsynced_feedback_events(limit: int = 100) -> list[dict]:
    """Return events ready to mirror to LangSmith: a known run_id, and — for
    chat_sent — a classified intent. Used by the feedback batch job."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, event_type, message, intent, langsmith_run_id
                FROM feedback_events
                WHERE langsmith_synced = FALSE
                  AND langsmith_run_id IS NOT NULL
                  AND (event_type != 'chat_sent' OR intent IS NOT NULL)
                ORDER BY created_at
                LIMIT %s
            """, (limit,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def mark_event_synced(event_id: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE feedback_events SET langsmith_synced = TRUE WHERE id = %s", (event_id,))


# ── Parent blocks ──────────────────────────────────────────────────────────────

def fetch_parent_block(parent_id: str, ticker: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT full_text, page, r2_key
                FROM parent_blocks
                WHERE parent_id = %s AND ticker = %s
            """, (parent_id, ticker))
            row = cur.fetchone()
            return {"full_text": row[0], "page": row[1], "r2_key": row[2]} if row else None
