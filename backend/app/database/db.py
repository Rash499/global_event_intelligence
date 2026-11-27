"""SQLite connection lifecycle, migration bootstrap and retention.

The connection path is derived from ``Settings.database_url`` so the documented
configuration is the only source of truth.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)

# ``DB_PATH`` is the configured database file. ``get_connection`` resolves its
# path at call time (rather than binding it at import) so tests can point a
# module-level ``DB_PATH`` at a temporary file and all layers follow.
DB_PATH = settings.ensure_data_dir()
BUSY_TIMEOUT_MS = settings.db_busy_timeout_ms


def current_db_path() -> Path:
    """Resolve the active database path.

    Module attribute first (patched by tests), otherwise the configured
    ``DATABASE_URL``. This keeps a single source of truth while remaining
    testable.
    """
    candidate = globals().get("DB_PATH")
    if candidate:
        return Path(candidate)
    return settings.db_path


def _safe_round(value, digits):
    """NULL-safe replacement for SQLite's ``round()``.

    ``round(NULL, 2)`` is NULL in SQLite, and SQLite refuses to hand NULL to a
    user-defined function ("user-defined function raised exception" -> 500).
    Wrapping the call keeps aggregates over empty/sparse tables returning NULL
    instead of failing, which is what the API contracts promise.
    """
    if value is None:
        return None
    try:
        return round(float(value), int(digits))
    except (TypeError, ValueError):
        return None


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a configured connection (row factory, busy timeout, WAL)."""
    path = Path(db_path) if db_path else current_db_path()
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    # Registered on every connection so aggregate rounding stays NULL-safe on
    # any SQLite build (behaviour differs across versions and distributions).
    conn.create_function("round", 2, _safe_round, deterministic=True)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    # Foreign keys are off by default in SQLite and must be enabled per
    # connection.
    conn.execute("PRAGMA foreign_keys = ON")
    if settings.db_wal_enabled:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error:
            # A database on a filesystem without WAL support still works.
            logger.warning("WAL mode unavailable for %s; continuing", path)
    return conn


@contextmanager
def write_connection(db_path: Path | None = None):
    """Yield a connection holding the write lock for the whole block.

    ``sqlite3`` opens transactions in *deferred* mode, so a read-then-write
    transaction has to upgrade its lock and can fail with ``SQLITE_BUSY``
    immediately (the busy timeout does not apply to upgrades). Ingestion reads
    existing articles and then inserts, so the lock is taken up front with
    ``BEGIN IMMEDIATE`` and the busy timeout then applies.
    """
    conn = get_connection(db_path)
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


@contextmanager
def read_connection(db_path: Path | None = None):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def backup_database(reason: str = "manual") -> dict:
    """Copy the database file next to itself with a timestamped name.

    Called before destructive migrations. SQLite's own backup API is used so a
    consistent snapshot is taken even with WAL files present.
    """
    source = current_db_path()
    if not source.exists():
        return {"created": False, "reason": "database does not exist yet"}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = source.with_name(f"{source.stem}.{stamp}.{reason}.bak")
    try:
        src = sqlite3.connect(source)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    except sqlite3.Error:
        shutil.copy2(source, target)
    return {"created": True, "path": str(target)}


HISTORICAL_RETENTION_DAYS = max(1, settings.historical_retention_days)


def purge_expired_events(retention_days: int | None = None) -> int:
    """Delete events older than the retention window plus their dependants.

    Returns the number of deleted events. Child tables that reference
    ``events(id)`` with ``ON DELETE CASCADE`` are cleaned by SQLite, but the
    explicit deletes are kept for databases migrated from older schemas where
    the cascade was not declared.
    """
    days = max(1, retention_days or HISTORICAL_RETENTION_DAYS)
    with write_connection() as conn:
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
                ) < julianday('now', '-' || ? || ' days')
                """,
                (days,),
            ).fetchall()
        ]

        if not expired_ids:
            return 0

        placeholders = ",".join("?" for _ in expired_ids)
        # Tables keyed by event_id, plus relationship/graph tables whose event
        # column is named differently. Only tables that actually carry the
        # column are touched, so the purge keeps working as the schema grows.
        child_tables = (
            "event_articles",
            "event_likes",
            "event_comments",
            "event_claims",
            "event_locations",
            "event_timeline",
            "event_entity_mentions",
            "alerts",
        )
        for table in child_tables:
            if _table_exists(conn, table) and _column_exists(conn, table, "event_id"):
                conn.execute(
                    f"DELETE FROM {table} WHERE event_id IN ({placeholders})",
                    expired_ids,
                )
        for table, column in (
            ("event_relationships", "source_event_id"),
            ("event_relationships", "target_event_id"),
        ):
            if _table_exists(conn, table) and _column_exists(conn, table, column):
                conn.execute(
                    f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
                    expired_ids,
                )

        conn.execute(f"DELETE FROM events WHERE id IN ({placeholders})", expired_ids)

        # Prune orphan articles (no event links) older than the article window.
        conn.execute(
            """
            DELETE FROM articles
            WHERE NOT EXISTS (
                SELECT 1 FROM event_articles ea WHERE ea.article_id = articles.id
            )
              AND julianday(COALESCE(published_at, first_seen_at, CURRENT_TIMESTAMP))
                  < julianday('now', '-' || ? || ' days')
            """,
            (max(1, settings.retention_article_days),),
        )
        return len(expired_ids)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def init_db() -> dict:
    """Create/upgrade the schema through the versioned migration runner."""
    from .migrations import run_migrations

    return run_migrations()
