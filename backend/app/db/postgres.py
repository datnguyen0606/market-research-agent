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
            # One-time migration: drop old ticker-based tables if they still exist.
            # CREATE TABLE IF NOT EXISTS won't replace them, but the new indexes
            # reference doc_id which doesn't exist in the old schema.
            # feedback_events, report_quality, and checkpoint tables are unaffected.
            cur.execute("""
                DO $$
                BEGIN
                  IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'documents' AND column_name = 'ticker'
                  ) THEN
                    DROP TABLE IF EXISTS parent_blocks;
                    DROP TABLE IF EXISTS documents;
                    RAISE NOTICE 'init_schema: dropped old ticker-based tables, recreating with doc_id schema';
                  END IF;
                END $$;
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id          TEXT         PRIMARY KEY,
                    filename        TEXT         NOT NULL,
                    file_type       VARCHAR(10),
                    r2_key          TEXT,
                    pages_processed INT,
                    chunks_stored   INT,
                    uploaded_at     TIMESTAMPTZ  DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS parent_blocks (
                    parent_id   TEXT         PRIMARY KEY,
                    doc_id      TEXT         NOT NULL,
                    full_text   TEXT         NOT NULL,
                    page        INT,
                    filename    TEXT,
                    r2_key      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_parent_blocks_doc_id
                ON parent_blocks(doc_id);

                CREATE TABLE IF NOT EXISTS report_quality (
                    thread_id           TEXT PRIMARY KEY,
                    langsmith_run_id    TEXT,
                    overall             FLOAT,
                    factual_accuracy    FLOAT,
                    logical_consistency FLOAT,
                    completeness        FLOAT,
                    sentiment_alignment FLOAT,
                    judge_passed        BOOLEAN,
                    created_at          TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_report_quality_created_at
                ON report_quality(created_at);

                CREATE TABLE IF NOT EXISTS feedback_events (
                    id                SERIAL PRIMARY KEY,
                    thread_id         TEXT         NOT NULL,
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

def insert_document(
    doc_id: str,
    filename: str,
    file_type: str,
    r2_key: str,
    pages: int,
    chunks: int,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documents (doc_id, filename, file_type, r2_key, pages_processed, chunks_stored)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE
                    SET pages_processed = EXCLUDED.pages_processed,
                        chunks_stored   = EXCLUDED.chunks_stored,
                        uploaded_at     = NOW()
            """, (doc_id, filename, file_type, r2_key, pages, chunks))


# ── Parent blocks ──────────────────────────────────────────────────────────────

def insert_parent_blocks(doc_id: str, chunks: list[dict], r2_key: str, filename: str = "") -> None:
    parents = [c for c in chunks if c["type"] == "parent"]
    if not parents:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            for block in parents:
                cur.execute("""
                    INSERT INTO parent_blocks (parent_id, doc_id, full_text, page, filename, r2_key)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (parent_id) DO UPDATE
                        SET full_text = EXCLUDED.full_text,
                            page      = EXCLUDED.page,
                            r2_key    = EXCLUDED.r2_key
                """, (block["id"], doc_id, block["text"], block["page"], filename, r2_key))


def fetch_parent_block(parent_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT full_text, page, filename, r2_key
                FROM parent_blocks
                WHERE parent_id = %s
            """, (parent_id,))
            row = cur.fetchone()
            return {"full_text": row[0], "page": row[1], "filename": row[2], "r2_key": row[3]} if row else None


# ── Feedback events (implicit, behavior-based) ────────────────────────────────

def insert_feedback_event(
    thread_id: str,
    event_type: str,
    message: str | None = None,
    langsmith_run_id: str | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO feedback_events (thread_id, event_type, message, langsmith_run_id)
                VALUES (%s, %s, %s, %s)
            """, (thread_id, event_type, message, langsmith_run_id))


def fetch_unclassified_chat_events(limit: int = 100) -> list[dict]:
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
