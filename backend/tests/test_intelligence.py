from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.intelligence.classification import normalize_category, classify_article
from app.intelligence.confidence import score_event_confidence
from app.intelligence.deduplication import is_duplicate
from app.intelligence.importance import score_event_importance
from app.main import app
from app.intelligence.verification import determine_corroboration_level


client = TestClient(app)


def test_same_url_is_duplicate():
    article = {"url": "https://example.com/flood", "title": "Flooding in Japan", "source": "Reuters"}
    assert is_duplicate(article, article) is True


def test_similar_title_is_possible_duplicate():
    a = {"url": "https://example.com/flood-1", "title": "Major flooding in Japan", "source": "Reuters", "published_at": "2025-01-01T12:00:00Z"}
    b = {"url": "https://example.com/flood-2", "title": "Flooding hits Japan causing emergency", "source": "BBC", "published_at": "2025-01-01T13:00:00Z"}
    assert is_duplicate(a, b) is True


def test_different_event_is_not_duplicate():
    a = {"url": "https://example.com/flood", "title": "Flooding in Japan", "source": "Reuters"}
    b = {"url": "https://example.com/election", "title": "Election results announced in Japan", "source": "AP"}
    assert is_duplicate(a, b) is False


# ---------------------------------------------------------------------------
# Regression: 500 responses must keep their CORS headers
# ---------------------------------------------------------------------------


def test_unhandled_error_response_keeps_cors_headers():
    """A failing endpoint must not surface in the browser as a CORS error.

    Starlette renders unhandled exceptions in ``ServerErrorMiddleware``, which
    sits outside ``CORSMiddleware``. A handler registered with
    ``@app.exception_handler(Exception)`` therefore produced a 500 with no
    ``Access-Control-Allow-Origin`` header, and the browser reported a
    perfectly healthy backend as blocked by CORS policy.
    """
    @app.get("/_test_boom")
    async def _boom():
        raise RuntimeError("intentional test failure")

    # raise_server_exceptions=False exercises the real 500 path.
    boom_client = TestClient(app, raise_server_exceptions=False)
    response = boom_client.get(
        "/_test_boom", headers={"Origin": "http://localhost:5173"}
    )

    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )
    # The client gets a readable message, never a stack trace.
    assert "detail" in response.json()
    assert "Traceback" not in response.text


def test_successful_response_keeps_cors_headers():
    """The normal path must keep working (guard against ordering mistakes)."""
    ok_client = TestClient(app, raise_server_exceptions=False)
    response = ok_client.get("/", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )


def test_cors_preflight_is_answered():
    """The browser preflight for the ingestion POST must be handled."""
    preflight = client.options(
        "/api/ingestion/run",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )
    assert "POST" in preflight.headers.get("access-control-allow-methods", "")


# ---------------------------------------------------------------------------
# Regression: concurrent writers must not fail with "database is locked"
# ---------------------------------------------------------------------------


def test_write_connection_waits_instead_of_failing(tmp_path, monkeypatch):
    """``write_connection`` must not raise "database is locked" under contention.

    A deferred transaction that reads first and writes later tries to *upgrade*
    a read lock to a write lock, and SQLite fails that immediately without
    honouring ``busy_timeout``. Taking the write lock up front with
    ``BEGIN IMMEDIATE`` makes the busy timeout apply.
    """
    import sqlite3
    import threading

    from app.database import db as db_module

    db_path = tmp_path / "contended.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    setup = db_module.get_connection()
    setup.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    setup.commit()
    setup.close()

    started = threading.Event()
    release = threading.Event()
    errors = []

    def hold_the_write_lock():
        holder = db_module.get_connection()
        holder.execute("BEGIN IMMEDIATE")
        holder.execute("INSERT INTO t (v) VALUES ('holder')")
        started.set()
        release.wait(10)
        holder.execute("COMMIT")
        holder.close()

    thread = threading.Thread(target=hold_the_write_lock)
    thread.start()
    assert started.wait(10), "helper thread never took the write lock"

    def do_a_write():
        try:
            with db_module.write_connection() as conn:
                conn.execute("INSERT INTO t (v) VALUES ('waiter')")
        except sqlite3.OperationalError as exc:  # pragma: no cover - failure path
            errors.append(str(exc))
        finally:
            release.set()

    writer = threading.Thread(target=do_a_write)
    writer.start()
    writer.join(20)

    release.set()
    thread.join(10)

    assert not errors, f"write_connection failed under contention: {errors}"

    check = db_module.get_connection()
    values = [row["v"] for row in check.execute("SELECT v FROM t").fetchall()]
    check.close()
    assert "waiter" in values


def test_normalize_category_handles_known_name():
    assert normalize_category("Natural Disaster") == "natural_disaster"
    assert normalize_category("nonsense") == "other"


def test_classification_uses_fallback_for_unrecognized_value():
    result = classify_article({"title": "Flooding causes major disruption in Japan", "description": "Flood waters forced evacuations"})
    assert result["category"] == "natural_disaster"


def test_higher_impact_event_scores_higher():
    low = score_event_importance({"severity": 2, "geographic_impact": 1, "source_coverage": 1, "human_impact": 1, "economic_impact": 1, "urgency": 2})
    high = score_event_importance({"severity": 9, "geographic_impact": 8, "source_coverage": 7, "human_impact": 9, "economic_impact": 6, "urgency": 8})
    assert high > low


def test_multiple_sources_increase_confidence():
    single = score_event_confidence({"source_count": 1, "article_count": 1, "classification_confidence": 0.7, "location_confidence": 0.8, "time_confidence": 0.7})
    multiple = score_event_confidence({"source_count": 5, "article_count": 8, "classification_confidence": 0.9, "location_confidence": 0.9, "time_confidence": 0.9})
    assert multiple > single


def test_multiple_independent_sources_have_stronger_corroboration():
    assert determine_corroboration_level(1) == "single"
    assert determine_corroboration_level(2) == "corroborated"
    assert determine_corroboration_level(5) == "strong"


def test_statistics_overview_includes_timeline_and_category_breakdown():
    response = client.get("/api/statistics/overview")

    assert response.status_code == 200
    payload = response.json()

    assert "total_events" in payload
    assert "categories" in payload
    assert "countries_by_event_count" in payload
    assert "timeline" in payload
    assert isinstance(payload["timeline"], list)
