"""Versioned database migrations.

``CREATE TABLE IF NOT EXISTS`` cannot express a schema change, so the database
now carries a ``schema_migrations`` ledger and every structural change is an
explicit, ordered, idempotent migration.

Rules that the runner enforces:

* migrations are applied in ascending version order inside one transaction each;
* a version recorded in the ledger is never applied twice;
* each migration is idempotent (``IF NOT EXISTS`` / column checks) so a
  partially applied database can be repaired;
* destructive migrations request a backup first via ``Migration(backup=True)``;
* existing databases created by the pre-migration code are adopted: migration
  ``001`` is the original bootstrap schema, so an existing file simply gets the
  ledger row and then receives ``002`` onwards.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Callable

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]
    # Request a file backup before running (schema rewrites, data moves).
    backup: bool = False
    notes: str = ""


# ----------------------------------------------------------------------
# Helpers used by migrations
# ----------------------------------------------------------------------
def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


def add_column(
    conn: sqlite3.Connection, table: str, column: str, ddl: str
) -> None:
    """Add a column only when it is missing (idempotent)."""
    if column in _columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def add_index(conn: sqlite3.Connection, name: str, target: str) -> None:
    conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")


def _exec(conn: sqlite3.Connection, sql: str) -> None:
    conn.executescript(sql)


# ----------------------------------------------------------------------
# 001 - original bootstrap schema (adopted as-is by existing databases)
# ----------------------------------------------------------------------
BOOTSTRAP_SQL = """
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

CREATE TABLE IF NOT EXISTS event_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    article_id INTEGER,
    claim_type TEXT,
    value TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
    ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_event_comments_event
    ON event_comments(event_id);
CREATE INDEX IF NOT EXISTS idx_event_likes_event
    ON event_likes(event_id);
CREATE INDEX IF NOT EXISTS idx_events_event_time
    ON events(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_country_time
    ON events(country_code, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_category_time
    ON events(category, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_event_articles_article
    ON event_articles(article_id);
"""


def _m001_bootstrap(conn: sqlite3.Connection) -> None:
    _exec(conn, BOOTSTRAP_SQL)
    add_column(conn, "articles", "image_url", "TEXT")
    for column, ddl in {
        "article_count": "INTEGER DEFAULT 1",
        "source_count": "INTEGER DEFAULT 1",
        "unique_source_count": "INTEGER DEFAULT 1",
        "corroboration_level": "TEXT DEFAULT 'single'",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "source_domains": "TEXT",
    }.items():
        add_column(conn, "events", column, ddl)


# ----------------------------------------------------------------------
# 002 - article provenance and normalisation
# ----------------------------------------------------------------------
def _m002_article_provenance(conn: sqlite3.Connection) -> None:
    for column, ddl in {
        "canonical_url": "TEXT",
        "publisher": "TEXT",
        "publisher_domain": "TEXT",
        "provider": "TEXT",
        "provider_record_id": "TEXT",
        "language": "TEXT",
        "author": "TEXT",
        "description_hash": "TEXT",
        "extraction_status": "TEXT DEFAULT 'metadata'",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "reporting_type": "TEXT DEFAULT 'direct'",
        "syndication_of": "TEXT",
        "event_time": "TEXT",
        "event_time_precision": "TEXT DEFAULT 'unknown'",
        "raw_metadata": "TEXT",
        "is_independent": "INTEGER DEFAULT 1",
        "source_record_at": "TEXT",
        "updated_at": "TEXT",
    }.items():
        add_column(conn, "articles", column, ddl)

    add_index(conn, "idx_articles_publisher", "articles(publisher_domain)")
    add_index(conn, "idx_articles_provider", "articles(provider)")
    add_index(conn, "idx_articles_published", "articles(published_at DESC)")
    add_index(conn, "idx_articles_first_seen", "articles(first_seen_at)")
    add_index(conn, "idx_articles_content_hash", "articles(content_hash)")
    add_index(conn, "idx_articles_canonical", "articles(canonical_url)")

    # Backfill: existing rows get the only provenance we can honestly derive.
    conn.execute(
        """
        UPDATE articles
        SET canonical_url = COALESCE(canonical_url, url),
            first_seen_at = COALESCE(first_seen_at, created_at, CURRENT_TIMESTAMP),
            last_seen_at = COALESCE(last_seen_at, CURRENT_TIMESTAMP)
        """
    ) if "created_at" in _columns(conn, "articles") else conn.execute(
        """
        UPDATE articles
        SET canonical_url = COALESCE(canonical_url, url),
            first_seen_at = COALESCE(first_seen_at, CURRENT_TIMESTAMP),
            last_seen_at = COALESCE(last_seen_at, CURRENT_TIMESTAMP)
        """
    )


# ----------------------------------------------------------------------
# 003 - event intelligence fields (taxonomy, lifecycle, assessment)
# ----------------------------------------------------------------------
def _m003_event_intelligence(conn: sqlite3.Connection) -> None:
    for column, ddl in {
        "subcategory": "TEXT",
        "taxonomy_version": "TEXT DEFAULT '1.0'",
        "classification_method": "TEXT DEFAULT 'deterministic'",
        "classification_confidence": "REAL",
        "severity": "REAL",
        "severity_label": "TEXT",
        "severity_components": "TEXT",
        "confidence_components": "TEXT",
        "confidence_explanation": "TEXT",
        "priority_score": "REAL",
        "priority_label": "TEXT",
        "location_precision": "TEXT DEFAULT 'unknown'",
        "location_text": "TEXT",
        "geocoding_source": "TEXT",
        "geocoding_confidence": "REAL",
        "event_state": "TEXT DEFAULT 'newly_detected'",
        "event_state_updated_at": "TEXT",
        "occurred_at": "TEXT",
        "occurred_at_precision": "TEXT DEFAULT 'unknown'",
        "observed_at": "TEXT",
        "updated_at": "TEXT",
        "assessment_updated_at": "TEXT",
        "independent_source_count": "INTEGER DEFAULT 0",
        "syndicated_source_count": "INTEGER DEFAULT 0",
        "ai_assessment": "TEXT",
        "ai_assessment_at": "TEXT",
        "ai_model": "TEXT",
        "escalation_trend": "TEXT",
        "provider_keys": "TEXT",
        "data_sources": "TEXT",
        "is_structured_observation": "INTEGER DEFAULT 0",
    }.items():
        add_column(conn, "events", column, ddl)

    add_index(conn, "idx_events_severity", "events(severity DESC)")
    add_index(conn, "idx_events_state", "events(event_state)")
    add_index(conn, "idx_events_subcategory", "events(category, subcategory)")
    add_index(conn, "idx_events_priority", "events(priority_score DESC)")
    add_index(conn, "idx_events_last_seen", "events(last_seen_at DESC)")
    add_index(conn, "idx_events_geo", "events(country_code, latitude, longitude)")

    # Sensible defaults for historical rows so analytics stay meaningful.
    conn.execute(
        """
        UPDATE events
        SET occurred_at = COALESCE(occurred_at, event_time, created_at),
            occurred_at_precision = COALESCE(occurred_at_precision, 'timestamp'),
            event_state = COALESCE(event_state, 'newly_detected'),
            taxonomy_version = COALESCE(taxonomy_version, '1.0'),
            independent_source_count = COALESCE(
                independent_source_count, unique_source_count, 0
            )
        WHERE occurred_at IS NULL OR event_state IS NULL
           OR taxonomy_version IS NULL OR independent_source_count IS NULL
        """
    )


# ----------------------------------------------------------------------
# 004 - provider registry, collection runs, scheduler jobs
# ----------------------------------------------------------------------
def _m004_providers(conn: sqlite3.Connection) -> None:
    _exec(
        conn,
        """
CREATE TABLE IF NOT EXISTS providers (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    enabled INTEGER DEFAULT 0,
    config_satisfied INTEGER DEFAULT 1,
    config_notes TEXT,
    docs_url TEXT,
    requires_credentials INTEGER DEFAULT 0,
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_error TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    circuit_open_until TEXT,
    avg_duration_ms REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_key TEXT NOT NULL,
    trigger TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms REAL,
    records_received INTEGER DEFAULT 0,
    records_accepted INTEGER DEFAULT 0,
    records_rejected INTEGER DEFAULT 0,
    records_duplicate INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    events_created INTEGER DEFAULT 0,
    events_updated INTEGER DEFAULT 0,
    error TEXT,
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_provider
    ON collection_runs(provider_key, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_collection_runs_started
    ON collection_runs(started_at DESC);
""",
    )


# ----------------------------------------------------------------------
# 005 - event relationships, locations, timeline, alerts, entities
# ----------------------------------------------------------------------
def _m005_intelligence_graph(conn: sqlite3.Connection) -> None:
    _exec(
        conn,
        """
CREATE TABLE IF NOT EXISTS event_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_event_id INTEGER NOT NULL,
    target_event_id INTEGER NOT NULL,
    relationship TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    reason TEXT,
    evidence TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_event_id, target_event_id, relationship)
);

CREATE INDEX IF NOT EXISTS idx_event_rel_source
    ON event_relationships(source_event_id);
CREATE INDEX IF NOT EXISTS idx_event_rel_target
    ON event_relationships(target_event_id);
CREATE INDEX IF NOT EXISTS idx_event_rel_type
    ON event_relationships(relationship);

CREATE TABLE IF NOT EXISTS event_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    country TEXT,
    country_code TEXT,
    latitude REAL,
    longitude REAL,
    precision TEXT NOT NULL DEFAULT 'unknown',
    confidence REAL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, name)
);

CREATE INDEX IF NOT EXISTS idx_event_locations_event
    ON event_locations(event_id);

CREATE TABLE IF NOT EXISTS event_timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    change_type TEXT NOT NULL,
    description TEXT NOT NULL,
    article_id INTEGER,
    confidence REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_event_timeline_event
    ON event_timeline(event_id, occurred_at);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,
    country_code TEXT,
    description TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    mention_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_country ON entities(country_code);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    UNIQUE(entity_id, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_alias
    ON entity_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS event_entity_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    article_id INTEGER,
    role TEXT,
    confidence REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_event_entity_event
    ON event_entity_mentions(event_id);
CREATE INDEX IF NOT EXISTS idx_event_entity_entity
    ON event_entity_mentions(entity_id);

CREATE TABLE IF NOT EXISTS entity_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    confidence REAL,
    evidence TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_entity_id, target_entity_id, relationship)
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    country_code TEXT,
    category TEXT,
    subcategory TEXT,
    min_severity REAL,
    min_confidence REAL,
    min_magnitude REAL,
    event_state TEXT,
    entity TEXT,
    keywords TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_evaluated_at TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER,
    event_id INTEGER NOT NULL,
    triggered_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    severity REAL,
    confidence REAL,
    title TEXT,
    reason TEXT,
    evidence TEXT,
    acknowledged_at TEXT,
    resolved_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(rule_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_event ON alerts(event_id);

CREATE TABLE IF NOT EXISTS saved_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    name TEXT NOT NULL,
    query TEXT,
    filters TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    name TEXT NOT NULL,
    country_codes TEXT,
    categories TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL,
    dimension TEXT NOT NULL,
    key TEXT,
    window_hours INTEGER NOT NULL,
    observed INTEGER NOT NULL,
    baseline REAL NOT NULL,
    expected REAL NOT NULL,
    deviation REAL NOT NULL,
    score REAL NOT NULL,
    independent_sources INTEGER DEFAULT 0,
    confidence REAL,
    explanation TEXT,
    sample_event_ids TEXT,
    dismissed INTEGER DEFAULT 0,
    UNIQUE(dimension, key, window_hours, detected_at)
);

CREATE INDEX IF NOT EXISTS idx_anomalies_detected
    ON anomalies(detected_at DESC);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    title TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_value TEXT,
    period_start TEXT,
    period_end TEXT,
    body TEXT NOT NULL,
    format TEXT DEFAULT 'json',
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
""",
    )


# ----------------------------------------------------------------------
# 006 - foreign keys on the pre-existing relationship tables
# ----------------------------------------------------------------------
def _m006_foreign_keys(conn: sqlite3.Connection) -> None:
    """Recreate ``event_articles``/``event_likes``/``event_comments`` with
    ``ON DELETE CASCADE``.

    Existing rows are copied across verbatim; no record is dropped. Rows that
    point at a deleted event are removed (they were already unreachable) after
    being counted in the log.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table, ddl, copy_columns in (
            (
                "event_articles",
                """CREATE TABLE event_articles_new (
                    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                    PRIMARY KEY(event_id, article_id)
                )""",
                "event_id, article_id",
            ),
            (
                "event_likes",
                """CREATE TABLE event_likes_new (
                    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(event_id, user_id)
                )""",
                "event_id, user_id, created_at",
            ),
            (
                "event_comments",
                """CREATE TABLE event_comments_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    author TEXT,
                    body TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                "id, event_id, user_id, author, body, created_at",
            ),
        ):
            if table not in _tables(conn):
                continue
            conn.execute(ddl)
            conn.execute(
                f"INSERT OR IGNORE INTO {table}_new ({copy_columns}) "
                f"SELECT {copy_columns} FROM {table}"
            )
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

        _exec(
            conn,
            """
CREATE INDEX IF NOT EXISTS idx_event_articles_article
    ON event_articles(article_id);
CREATE INDEX IF NOT EXISTS idx_event_articles_event
    ON event_articles(event_id);
CREATE INDEX IF NOT EXISTS idx_event_comments_event
    ON event_comments(event_id);
CREATE INDEX IF NOT EXISTS idx_event_likes_event
    ON event_likes(event_id);
""",
        )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _m007_source_credibility(conn: sqlite3.Connection) -> None:
    for column, ddl in {
        "source_tier": "TEXT DEFAULT 'undeclared'",
        "propaganda_risk": "TEXT DEFAULT 'medium'",
        "state_affiliated": "INTEGER DEFAULT 0",
        "source_region": "TEXT",
    }.items():
        add_column(conn, "articles", column, ddl)
    add_column(conn, "events", "credibility_score", "INTEGER")
    add_index(conn, "idx_events_credibility", "events(credibility_score)")


def _m008_importance_alert_preferences(conn: sqlite3.Connection) -> None:
    add_column(conn, "events", "importance_score", "REAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_alert_preferences (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            sensitivity TEXT NOT NULL DEFAULT 'critical_and_high'
                CHECK (sensitivity IN ('critical_only', 'critical_and_high')),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_event_suppressions (
            event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
            suppressed_until TEXT NOT NULL,
            severity TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    add_column(conn, "providers", "consecutive_empty_runs", "INTEGER DEFAULT 0")


def _m009_region_baselines(conn: sqlite3.Connection) -> None:
    add_column(conn, "anomalies", "severity", "TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS region_baseline_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL,
            bucket_kind TEXT NOT NULL CHECK(bucket_kind IN ('weekday','month')),
            bucket_key TEXT NOT NULL,
            sample_date TEXT NOT NULL,
            observed_count REAL NOT NULL,
            sample_event_ids TEXT NOT NULL DEFAULT '[]',
            UNIQUE(region,bucket_kind,bucket_key,sample_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS region_baselines (
            region TEXT NOT NULL,
            bucket_kind TEXT NOT NULL,
            bucket_key TEXT NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0,
            mean REAL NOT NULL DEFAULT 0,
            m2 REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(region,bucket_kind,bucket_key)
        )
    """)
    add_index(conn, "idx_region_baseline_sample_date", "region_baseline_samples(sample_date)")
    add_index(conn, "idx_region_baselines_region", "region_baselines(region,bucket_kind)")


def _m010_digest_snapshots(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS digest_snapshots (
            snapshot_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            generated_at TEXT NOT NULL
        )
    """)


def _m011_anomaly_z_score(conn: sqlite3.Connection) -> None:
    add_column(conn, "anomalies", "z_score", "REAL")


MIGRATIONS: list[Migration] = [
    Migration(1, "bootstrap_schema", _m001_bootstrap),
    Migration(2, "article_provenance", _m002_article_provenance),
    Migration(3, "event_intelligence_fields", _m003_event_intelligence),
    Migration(4, "provider_registry", _m004_providers),
    Migration(5, "intelligence_graph", _m005_intelligence_graph),
    Migration(6, "relationship_foreign_keys", _m006_foreign_keys, backup=True),
    Migration(7, "source_credibility", _m007_source_credibility),
    Migration(8, "importance_and_alert_preferences", _m008_importance_alert_preferences),
    Migration(9, "region_baselines", _m009_region_baselines),
    Migration(10, "digest_snapshots", _m010_digest_snapshots),
    Migration(11, "anomaly_z_score", _m011_anomaly_z_score),
]

LATEST_VERSION = max(m.version for m in MIGRATIONS)


def _ensure_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_ledger(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return int(row["v"] or 0)


def applied_versions(conn: sqlite3.Connection) -> list[dict]:
    _ensure_ledger(conn)
    return [
        dict(row)
        for row in conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]


def run_migrations(conn: sqlite3.Connection | None = None) -> dict:
    """Apply pending migrations. Returns a summary for logs/tests."""
    from .db import backup_database, get_connection

    owns_connection = conn is None
    if owns_connection:
        settings.ensure_data_dir()
        conn = get_connection()

    applied: list[int] = []
    backed_up: str | None = None
    try:
        _ensure_ledger(conn)
        conn.commit()
        version = current_version(conn)
        pending = [m for m in MIGRATIONS if m.version > version]

        if pending and any(m.backup for m in pending):
            if settings.db_backup_before_migration and not settings.is_test:
                result = backup_database("premigration")
                backed_up = result.get("path")

        for migration in pending:
            logger.info(
                "Applying migration %03d_%s", migration.version, migration.name
            )
            try:
                conn.execute("BEGIN")
                migration.apply(conn)
                conn.execute(
                    "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
                conn.commit()
                applied.append(migration.version)
            except sqlite3.Error as exc:
                conn.rollback()
                logger.exception(
                    "Migration %03d_%s failed", migration.version, migration.name
                )
                raise RuntimeError(
                    f"Database migration {migration.version}_{migration.name} failed: {exc}"
                ) from exc

        return {
            "from_version": version,
            "to_version": current_version(conn),
            "applied": applied,
            "pending": max(0, LATEST_VERSION - current_version(conn)),
            "backup": backed_up,
            "latest_version": LATEST_VERSION,
        }
    finally:
        if owns_connection and conn is not None:
            conn.close()


def verify_migrations(conn: sqlite3.Connection | None = None) -> dict:
    """Health check: report schema version and whether it is current."""
    from .db import get_connection

    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        version = current_version(conn)
        return {
            "current_version": version,
            "latest_version": LATEST_VERSION,
            "up_to_date": version >= LATEST_VERSION,
            "applied": applied_versions(conn),
        }
    finally:
        if owns_connection and conn is not None:
            conn.close()
