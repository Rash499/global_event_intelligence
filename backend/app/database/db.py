import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "events.db"

# Phase 3 indexing writes to the same SQLite file while the map/dashboard reads
# it. In the default rollback-journal mode a writer blocks every reader (and the
# other way round), which showed up as the whole app hanging during indexing.
# WAL lets readers and one writer work concurrently, and the busy timeout makes
# a contended write wait instead of failing immediately.
BUSY_TIMEOUT_MS = 30000


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.Error:
        # A database on a filesystem without WAL support still works.
        pass
    return conn


@contextmanager
def write_connection():
    """Yield a connection that holds the write lock for the whole block.

    ``sqlite3`` opens transactions in *deferred* mode: a transaction starts on
    the first statement and only takes a lock when it first writes. A reader
    therefore starts as a reader and later tries to *upgrade* to a writer.
    SQLite cannot always grant that upgrade - it returns ``SQLITE_BUSY``
    ("database is locked") immediately, and ``busy_timeout`` deliberately does
    **not** apply to it, because waiting could deadlock.

    Ingestion is the case that hits this: it reads the existing articles and
    events, then inserts, while the RAG indexer and the retention purge are
    writing in parallel. Acquiring the write lock up front with
    ``BEGIN IMMEDIATE`` makes the busy timeout apply, so the writer waits for
    the lock instead of crashing the request.
    """
    conn = get_connection()
    # Take manual control of transactions so BEGIN IMMEDIATE is not fought over
    # by the driver's implicit transaction handling.
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


HISTORICAL_RETENTION_DAYS = 365


def purge_expired_events() -> int:
    # Use the same write-lock strategy as ingestion so retention cleanup waits
    # for another writer instead of failing with SQLITE_BUSY.
    conn = get_connection()
    conn.isolation_level = None

    try:
        conn.execute("BEGIN IMMEDIATE")
        expired_ids = [
            row["id"]
            for row in conn.execute(
                """
                SELECT id
                FROM events
                WHERE julianday(
                    CASE
                        WHEN event_time IS NULL
                          OR TRIM(event_time) = ''
                          OR julianday(event_time) IS NULL
                        THEN created_at
                        ELSE event_time
                    END
                ) < julianday('now', '-365 days')
                """
            ).fetchall()
        ]

        if not expired_ids:
            return 0

        placeholders = ",".join("?" for _ in expired_ids)
        for table in ("event_articles", "event_likes", "event_comments"):
            conn.execute(
                f"DELETE FROM {table} WHERE event_id IN ({placeholders})",
                expired_ids,
            )

        conn.execute(
            f"DELETE FROM events WHERE id IN ({placeholders})",
            expired_ids,
        )
        conn.execute("COMMIT")
        return len(expired_ids)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        source TEXT,
        published_at TEXT,
        description TEXT,
        image_url TEXT,
        content_hash TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT,
        category TEXT NOT NULL,
        country TEXT,
        country_code TEXT,
        latitude REAL,
        longitude REAL,
        importance INTEGER DEFAULT 5,
        confidence REAL DEFAULT 0.5,
        article_count INTEGER DEFAULT 1,
        source_count INTEGER DEFAULT 1,
        unique_source_count INTEGER DEFAULT 1,
        corroboration_level TEXT DEFAULT 'single',
        first_seen_at TEXT,
        last_seen_at TEXT,
        source_domains TEXT,
        event_time TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS event_articles (
        event_id INTEGER NOT NULL,
        article_id INTEGER NOT NULL,
        PRIMARY KEY(event_id, article_id)
    );

    CREATE TABLE IF NOT EXISTS event_likes (
        event_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(event_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS event_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        author TEXT,
        body TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
        ON auth_sessions(user_id);

    CREATE INDEX IF NOT EXISTS idx_event_comments_event
        ON event_comments(event_id);

    CREATE INDEX IF NOT EXISTS idx_event_likes_event
        ON event_likes(event_id);

    -- Phase 1/2 read paths: latest events, per-country feeds and the assistant's
    -- filtered retrieval all sort/filter on these columns.
    CREATE INDEX IF NOT EXISTS idx_events_event_time
        ON events(event_time DESC);

    CREATE INDEX IF NOT EXISTS idx_events_country_time
        ON events(country_code, event_time DESC);

    CREATE INDEX IF NOT EXISTS idx_events_category_time
        ON events(category, event_time DESC);

    CREATE INDEX IF NOT EXISTS idx_event_articles_article
        ON event_articles(article_id);
    """)

    article_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }
    if "image_url" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")

    event_columns = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    for column_name, column_sql in {
        "article_count": "INTEGER DEFAULT 1",
        "source_count": "INTEGER DEFAULT 1",
        "unique_source_count": "INTEGER DEFAULT 1",
        "corroboration_level": "TEXT DEFAULT 'single'",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "source_domains": "TEXT",
    }.items():
        if column_name not in event_columns:
            conn.execute(f"ALTER TABLE events ADD COLUMN {column_name} {column_sql}")

    conn.commit()
    conn.close()
