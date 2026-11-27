"""Configuration, database and migration tests (Phase 1 foundation)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.config import Settings


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
def test_database_url_relative_path_is_under_backend():
    settings = Settings(database_url="sqlite:///./data/events.db")
    assert settings.db_path.name == "events.db"
    assert settings.db_path.parent.name == "data"
    assert settings.db_path.is_absolute()


def test_database_url_absolute_path_is_preserved():
    settings = Settings(database_url="sqlite:////var/lib/gei/events.db")
    assert str(settings.db_path) == "/var/lib/gei/events.db"


def test_database_url_is_the_single_source_of_truth(tmp_path):
    """The documented DATABASE_URL must actually decide the connection path."""
    from app.database import db as db_module

    target = tmp_path / "explicit.db"
    settings = Settings(database_url=f"sqlite:///{target}")
    assert settings.db_path == target


def test_non_sqlite_database_url_is_rejected():
    with pytest.raises(Exception):
        Settings(database_url="postgresql://user:pw@localhost/db")


def test_invalid_environment_is_rejected():
    with pytest.raises(Exception):
        Settings(environment="staging")


def test_production_rejects_demo_data():
    with pytest.raises(Exception):
        Settings(environment="production", demo_data_enabled=True)


def test_production_rejects_wildcard_cors():
    with pytest.raises(Exception):
        Settings(environment="production", cors_origins="*")


def test_cors_origins_are_parsed():
    settings = Settings(cors_origins="http://a.test, http://b.test ,")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_syndication_domain_set_is_normalised():
    settings = Settings(syndication_domains="News.Google.com, msn.com ")
    assert "news.google.com" in settings.syndication_domain_set


# ----------------------------------------------------------------------
# Migrations
# ----------------------------------------------------------------------
def test_migrations_create_full_schema(tmp_path):
    from app.database import db as db_module
    from app.database.migrations import LATEST_VERSION, run_migrations, verify_migrations

    path = tmp_path / "fresh.db"
    conn = db_module.get_connection(path)
    try:
        summary = run_migrations(conn)
        assert summary["to_version"] == LATEST_VERSION
        assert summary["pending"] == 0
        assert verify_migrations(conn)["up_to_date"] is True

        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for expected in (
            "events", "articles", "event_articles", "schema_migrations",
            "providers", "collection_runs", "event_relationships", "event_timeline",
            "entities", "alert_rules", "alerts", "anomalies", "reports",
            "event_locations", "saved_searches", "watchlists",
        ):
            assert expected in tables, f"missing table {expected}"
    finally:
        conn.close()


def test_migrations_are_idempotent(tmp_path):
    from app.database import db as db_module
    from app.database.migrations import run_migrations

    path = tmp_path / "repeat.db"
    conn = db_module.get_connection(path)
    try:
        first = run_migrations(conn)
        second = run_migrations(conn)
        assert first["applied"]
        assert second["applied"] == []
    finally:
        conn.close()


def test_existing_legacy_database_is_adopted_without_data_loss(tmp_path):
    """A database created by the old CREATE TABLE code must keep its rows."""
    from app.database import db as db_module
    from app.database.migrations import run_migrations

    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, summary TEXT,
            category TEXT NOT NULL, country TEXT, country_code TEXT, latitude REAL,
            longitude REAL, importance INTEGER DEFAULT 5, confidence REAL DEFAULT 0.5,
            article_count INTEGER DEFAULT 1, source_count INTEGER DEFAULT 1,
            unique_source_count INTEGER DEFAULT 1, corroboration_level TEXT DEFAULT 'single',
            first_seen_at TEXT, last_seen_at TEXT, source_domains TEXT,
            event_time TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL, source TEXT, published_at TEXT,
            description TEXT, image_url TEXT, content_hash TEXT
        );
        INSERT INTO events (title, category, country_code, event_time)
            VALUES ('Legacy flood event', 'environment', 'LK', '2026-01-01T00:00:00Z');
        INSERT INTO articles (title, url) VALUES ('Legacy article', 'https://legacy.example/1');
        """
    )
    legacy.commit()
    legacy.close()

    conn = db_module.get_connection(path)
    try:
        run_migrations(conn)
        row = conn.execute("SELECT title, category FROM events").fetchone()
        assert row["title"] == "Legacy flood event"
        # Legacy category is preserved; the taxonomy maps it at read time.
        assert row["category"] == "environment"
        assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1
        # New columns were backfilled, not nulled out.
        assert conn.execute("SELECT occurred_at FROM events").fetchone()[0] is not None
    finally:
        conn.close()


def test_foreign_keys_cascade_on_event_delete(db_path):
    from app.database.db import get_connection

    conn = get_connection()
    try:
        event_id = conn.execute(
            "INSERT INTO events (title, category) VALUES ('Cascade', 'other')"
        ).lastrowid
        article_id = conn.execute(
            "INSERT INTO articles (title, url) VALUES ('A', 'https://x.example/1')"
        ).lastrowid
        conn.execute(
            "INSERT INTO event_articles (event_id, article_id) VALUES (?, ?)",
            (event_id, article_id),
        )
        conn.commit()
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM event_articles").fetchone()[0] == 0
    finally:
        conn.close()


def test_indexes_exist_for_query_paths(db_path):
    from app.database.db import get_connection

    conn = get_connection()
    try:
        indexes = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        conn.close()
    for expected in (
        "idx_events_event_time", "idx_events_country_time", "idx_events_category_time",
        "idx_events_severity", "idx_events_state", "idx_events_priority",
        "idx_events_geo", "idx_events_subcategory", "idx_articles_publisher",
        "idx_articles_published", "idx_collection_runs_provider", "idx_alerts_status",
    ):
        assert expected in indexes, f"missing index {expected}"


def test_retention_purge_removes_only_expired_events(db_path):
    from app.database.db import get_connection, purge_expired_events

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO events (title, category, event_time) "
            "VALUES ('Old', 'other', '2020-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO events (title, category, event_time) "
            "VALUES ('Recent', 'other', datetime('now'))"
        )
        conn.commit()
    finally:
        conn.close()

    deleted = purge_expired_events(retention_days=30)
    assert deleted == 1

    conn = get_connection()
    try:
        remaining = [row["title"] for row in conn.execute("SELECT title FROM events")]
    finally:
        conn.close()
    assert remaining == ["Recent"]
