"""Shared pytest fixtures.

Every test runs against a throwaway SQLite database created through the real
migration runner, so schema drift is caught by the suite. No test touches the
network, Ollama or a production database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Configure the environment before any application module is imported.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("RAG_ENABLED", "false")
os.environ.setdefault("OLLAMA_ENABLED", "false")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("DEMO_DATA_ENABLED", "false")
os.environ.setdefault("RAG_EMBEDDING_PROVIDER", "hashing")
os.environ.setdefault("RAG_VECTOR_STORE", "sqlite")


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Isolated database file wired into every layer."""
    from app.database import db as db_module

    path = tmp_path / "test-events.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    db_module.init_db()
    yield path


@pytest.fixture()
def conn(db_path):
    """Autocommit connection for fixtures.

    Deliberately *not* ``write_connection``: holding an open ``BEGIN IMMEDIATE``
    for the duration of a test would block the API's own writes (and hide the
    fixture rows from the request thread). Autocommit keeps the fixture rows
    visible immediately and releases the write lock after each statement.
    """
    from app.database.db import get_connection

    connection = get_connection()
    connection.isolation_level = None  # autocommit
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def client(db_path):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
