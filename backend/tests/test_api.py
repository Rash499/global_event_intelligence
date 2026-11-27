"""API behaviour: pagination, filtering, alerts, anomalies, reports, country intel."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest


def _iso(hours_ago: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


@pytest.fixture()
def seeded(conn):
    """Insert a small, realistic event set."""
    rows = [
        ("Magnitude 7.2 earthquake strikes Japan", "natural_disaster", "earthquake", "Japan", "JP", 35.0, 139.0, "exact", 9.1, 0.88, "critical", 9.2, 2),
        ("Protesters clash with police in Nairobi", "protest_unrest", "riot", "Kenya", "KE", -1.29, 36.82, "city", 5.2, 0.71, "moderate", 6.1, 3),
        ("Flooding displaces thousands in Sri Lanka", "natural_disaster", "flood", "Sri Lanka", "LK", None, None, "country", 6.4, 0.66, "high", 6.8, 5),
        ("Parliament passes budget in Brazil", "political_development", "legislative_development", "Brazil", "BR", None, None, "country", 3.1, 0.62, "moderate", 3.4, 9),
    ]
    for title, category, sub, country, code, lat, lon, precision, severity, confidence, label, priority, hours in rows:
        conn.execute(
            """
            INSERT INTO events (
                title, summary, category, subcategory, country, country_code,
                latitude, longitude, location_precision, severity, severity_label,
                confidence, priority_score, priority_label, importance, event_state,
                occurred_at, event_time, first_seen_at, last_seen_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ongoing', ?, ?, ?, ?, ?)
            """,
            (
                title, title, category, sub, country, code, lat, lon, precision,
                severity, label, confidence, priority, "elevated",
                round(severity), _iso(hours), _iso(hours), _iso(hours), _iso(hours), _iso(hours),
            ),
        )
    return conn


# ----------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------
def test_events_endpoint_returns_paginated_envelope(client, seeded):
    response = client.get("/api/events?limit=2")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["has_more"] is True
    assert body["next_cursor"]

    second = client.get("/api/events", params={"limit": 2, "cursor": body["next_cursor"]}).json()
    first_ids = {event["id"] for event in body["items"]}
    second_ids = {event["id"] for event in second["items"]}
    assert not (first_ids & second_ids)


def test_invalid_cursor_is_rejected(client, seeded):
    assert client.get("/api/events?cursor=not-a-cursor").status_code == 400


def test_event_filters(client, seeded):
    assert len(client.get("/api/events?category=natural_disaster").json()["items"]) == 2
    assert len(client.get("/api/events?country_code=JP").json()["items"]) == 1
    assert len(client.get("/api/events?min_severity=6").json()["items"]) == 2
    assert len(client.get("/api/events?min_confidence=0.8").json()["items"]) == 1
    assert len(client.get("/api/events?search=flood").json()["items"]) == 1


def test_event_sorting_by_severity(client, seeded):
    items = client.get("/api/events?sort=severity").json()["items"]
    severities = [event["severity"] for event in items]
    assert severities == sorted(severities, reverse=True)


def test_event_payload_exposes_precision_and_assessments(client, seeded):
    event = client.get("/api/events?country_code=LK").json()["items"][0]
    assert event["location"]["precision"] == "country"
    assert event["location"]["latitude"] is None  # no fabricated coordinates
    assert event["severity_label"] == "high"
    assert event["corroboration"]["level"] is not None


def test_event_detail_returns_sources_and_timeline(client, seeded, conn):
    event_id = conn.execute("SELECT id FROM events LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO articles (title, url, publisher, publisher_domain) VALUES (?,?,?,?)",
        ("Source article", "https://x.example/1", "Reuters", "reuters.com"),
    )
    article_id = conn.execute("SELECT id FROM articles LIMIT 1").fetchone()["id"]
    conn.execute("INSERT INTO event_articles (event_id, article_id) VALUES (?,?)", (event_id, article_id))
    conn.execute(
        "INSERT INTO event_timeline (event_id, occurred_at, change_type, description) VALUES (?,?,?,?)",
        (event_id, _iso(), "initial_report", "First report received."),
    )

    detail = client.get(f"/api/events/{event_id}").json()
    assert detail["sources"][0]["publisher"] == "Reuters"
    assert detail["timeline"][0]["change_type"] == "initial_report"
    assert "relationships" in detail
    assert "entities" in detail


def test_missing_event_returns_404(client, seeded):
    assert client.get("/api/events/999999").status_code == 404


# ----------------------------------------------------------------------
# Dashboard / statistics
# ----------------------------------------------------------------------
def test_dashboard_overview_uses_real_data(client, seeded):
    body = client.get("/api/dashboard/overview").json()
    assert body["totals"]["events"] == 4
    assert body["totals"]["critical_events"] == 1
    assert body["totals"]["countries_affected"] == 4
    assert body["coverage"]["events_with_coordinates"] == 2
    assert body["coverage"]["events_country_only"] == 2
    assert len(body["severity_distribution"]) == 6
    assert body["generated_at"]


def test_statistics_endpoint_is_unchanged_for_old_clients(client, seeded):
    body = client.get("/api/statistics/global").json()
    assert body["total_events"] == 4
    assert body["categories"]


# ----------------------------------------------------------------------
# Providers
# ----------------------------------------------------------------------
def test_providers_endpoint_lists_every_provider(client):
    body = client.get("/api/providers").json()
    keys = {item["provider"] for item in body["items"]}
    assert {"rss", "gdelt", "google_news", "usgs", "who", "reliefweb", "firms", "cap", "acled"} <= keys
    for item in body["items"]:
        assert item["status"] in {
            "healthy", "degraded", "unavailable", "not_configured", "disabled", "idle"
        }
        assert "last_success_at" in item
        assert "config_satisfied" in item


def test_unconfigured_providers_do_not_break_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


# ----------------------------------------------------------------------
# Country intelligence
# ----------------------------------------------------------------------
def test_country_risk_explains_methodology_and_coverage(client, seeded):
    body = client.get("/api/countries/JP/risk").json()
    assert body["country"] == "Japan"
    assert body["total_events"] == 1
    assert body["coverage"]["note"]
    assert body["methodology"]
    assert body["limitations"]
    dimensions = {dimension["dimension"]: dimension for dimension in body["dimensions"]}
    assert dimensions["conflict_security"]["event_count"] == 0
    assert dimensions["natural_disasters"]["event_count"] == 1


def test_country_without_reporting_is_not_described_as_safe(client, seeded):
    body = client.get("/api/countries/NO/risk").json()
    assert body["coverage"]["level"] == "none"
    assert "does not indicate that conditions are safe" in body["coverage"]["note"]


def test_unknown_country_code_is_404(client):
    assert client.get("/api/countries/ZZ/risk").status_code == 404


# ----------------------------------------------------------------------
# Alerts
# ----------------------------------------------------------------------
def test_alert_rule_creation_and_evaluation(client, seeded):
    created = client.post(
        "/api/alert-rules",
        json={"name": "Japan earthquakes", "country_code": "jp", "category": "natural_disaster", "min_severity": 7},
    )
    assert created.status_code == 201

    from app.alerts.evaluator import evaluate_all_rules

    assert evaluate_all_rules() == 1

    alerts = client.get("/api/alerts").json()
    assert alerts["items"]
    alert = alerts["items"][0]
    assert alert["rule_name"] == "Japan earthquakes"
    assert alert["evidence"]["reasons"]
    assert alert["status"] == "new"


def test_alert_evaluation_is_idempotent(client, seeded):
    client.post("/api/alert-rules", json={"name": "All disasters", "category": "natural_disaster"})
    from app.alerts.evaluator import evaluate_all_rules

    first = evaluate_all_rules()
    second = evaluate_all_rules()
    assert first == 2
    assert second == 0


def test_alert_status_transitions(client, seeded):
    client.post("/api/alert-rules", json={"name": "Any disaster", "category": "natural_disaster"})
    from app.alerts.evaluator import evaluate_all_rules

    evaluate_all_rules()
    alert_id = client.get("/api/alerts").json()["items"][0]["id"]

    response = client.post(f"/api/alerts/{alert_id}/status", json={"status": "acknowledged"})
    assert response.status_code == 200
    assert client.get("/api/alerts?status=acknowledged").json()["items"][0]["id"] == alert_id


def test_invalid_alert_status_is_rejected(client, seeded):
    assert client.post("/api/alerts/1/status", json={"status": "exploded"}).status_code == 422


def test_alert_rule_deletion(client):
    rule_id = client.post("/api/alert-rules", json={"name": "Temp"}).json()["id"]
    assert client.delete(f"/api/alert-rules/{rule_id}").status_code == 204
    assert client.get("/api/alert-rules").json()["items"] == []


# ----------------------------------------------------------------------
# Anomalies
# ----------------------------------------------------------------------
def test_anomaly_detection_requires_a_baseline(client, seeded):
    """A single busy window with no history must not raise an anomaly."""
    body = client.get("/api/anomalies").json()
    assert body["count"] == 0


def test_anomaly_is_detected_against_a_real_baseline(client, conn):
    now = datetime.now(timezone.utc)
    # Seven quiet windows, then a burst of 8 conflict events in the last window.
    for index in range(7):
        occurred = now - timedelta(hours=24 * (index + 1) + 6)
        for _ in range(2):
            conn.execute(
                "INSERT INTO events (title, category, country_code, occurred_at, event_time) "
                "VALUES ('Background', 'armed_conflict', 'UA', ?, ?)",
                (occurred.isoformat(), occurred.isoformat()),
            )
    burst_ids = []
    for _ in range(8):
        occurred = now - timedelta(hours=2)
        cursor = conn.execute(
            "INSERT INTO events (title, category, country_code, occurred_at, event_time) "
            "VALUES ('Burst event', 'armed_conflict', 'UA', ?, ?)",
            (occurred.isoformat(), occurred.isoformat()),
        )
        burst_ids.append(cursor.lastrowid)
    # Anomaly detection requires at least two independent publishers.
    for index, event_id in enumerate(burst_ids):
        conn.execute(
            "INSERT INTO articles (title, url, publisher_domain) VALUES (?,?,?)",
            (f"Report {index}", f"https://outlet{index}.example/a", f"outlet{index}.example"),
        )
        article_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute("INSERT INTO event_articles (event_id, article_id) VALUES (?,?)", (event_id, article_id))
    conn.execute(
        "INSERT INTO collection_runs (provider_key, trigger, status, started_at) VALUES ('rss','scheduled','healthy',?)",
        (_iso(1),),
    )

    body = client.get("/api/anomalies").json()
    assert body["count"] >= 1
    anomaly = body["items"][0]
    assert anomaly["dimension"] in {"category", "country"}
    assert anomaly["observed"] >= 8
    assert anomaly["expected"] < anomaly["observed"]
    assert anomaly["sample_event_ids"]


# ----------------------------------------------------------------------
# Reports and export
# ----------------------------------------------------------------------
def test_report_generation_contains_evidence_and_limitations(client, seeded):
    report = client.post("/api/reports", json={"scope": "global", "days": 30}).json()
    assert report["title"]
    assert report["all_events"]
    assert report["executive_summary"]
    assert report["methodology"]
    assert report["contradictions_and_uncertainty"]
    assert report["coverage"]


def test_report_export_csv_and_html(client, seeded):
    report_id = client.post("/api/reports", json={"scope": "country", "scope_value": "JP"}).json()["id"]

    csv_response = client.get(f"/api/reports/{report_id}/export?format=csv")
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "event_id" in csv_response.text

    html_response = client.get(f"/api/reports/{report_id}/export?format=html")
    assert html_response.status_code == 200
    assert "<html" in html_response.text
    assert "Methodology and limitations" in html_response.text


def test_unknown_report_is_404(client):
    assert client.get("/api/reports/999/export?format=csv").status_code == 404


def test_report_is_persisted(client, seeded):
    client.post("/api/reports", json={"scope": "global"})
    listed = client.get("/api/reports").json()["items"]
    assert len(listed) == 1


# ----------------------------------------------------------------------
# Search / saved searches / entities / system
# ----------------------------------------------------------------------
def test_unified_search_across_types(client, seeded):
    body = client.get("/api/search", params={"q": "Japan"}).json()
    assert body["events"]
    assert body["countries"][0]["country_code"] == "JP"


def test_saved_search_lifecycle(client):
    created = client.post("/api/saved-searches", json={"name": "Japan quakes", "query": "japan", "filters": {"category": "natural_disaster"}})
    assert created.status_code == 201
    listed = client.get("/api/saved-searches").json()["items"]
    assert listed[0]["filters"]["category"] == "natural_disaster"
    assert client.delete(f"/api/saved-searches/{created.json()['id']}").status_code == 204


def test_saved_search_requires_a_name(client):
    assert client.post("/api/saved-searches", json={"query": "x"}).status_code == 422


def test_entity_endpoints(client, seeded, conn):
    from app.intelligence.entities import extract_entities, upsert_entities

    event_id = conn.execute("SELECT id FROM events LIMIT 1").fetchone()["id"]
    upsert_entities(conn, event_id, extract_entities("The Ministry of Interior and NATO responded to Hezbollah."))

    listed = client.get("/api/entities").json()
    assert listed["count"] >= 3
    entity_id = listed["items"][0]["id"]
    detail = client.get(f"/api/entities/{entity_id}").json()
    assert detail["events"]
    assert "relationships" in detail


def test_entity_extraction_keeps_types_separate():
    from app.intelligence.entities import extract_entities

    entities = extract_entities("Georgia the country and Georgia the state disagree.")
    types = {entity["entity_type"] for entity in entities}
    assert "country" in types


def test_system_status_reports_migrations_and_scheduler(client):
    body = client.get("/api/system/status").json()
    assert body["database"]["available"] is True
    assert body["database"]["migrations"]["up_to_date"] is True
    assert "jobs" in body["scheduler"]
    assert body["security"]["demo_data_enabled"] is False


def test_taxonomy_endpoint(client):
    body = client.get("/api/taxonomy").json()
    assert body["version"] == "1.0"
    assert len(body["categories"]) == 16


# ----------------------------------------------------------------------
# Map layer: location precision must be explicit
# ----------------------------------------------------------------------
def test_map_layer_separates_coordinates_from_country_level(client, seeded):
    body = client.get("/api/map/events?days=7").json()

    plotted = {item["id"] for item in body["items"] if item["latitude"] is not None}
    assert plotted, "coordinate events should be returned"
    # Country-only rows may appear in the payload but must be labelled as such,
    # so the UI can shade a region instead of inventing a pin.
    for item in body["items"]:
        assert "location_precision" in item
        if item["location_precision"] == "country":
            assert item["latitude"] is None

    assert body["coverage"]["country_level_only"] >= 1
    assert body["coverage"]["plotted_with_coordinates"] >= 1
    assert body["legend"]["severity_bands"]


def test_map_layer_precision_filter(client, seeded):
    coords = client.get("/api/map/events?days=7&precision=coordinates").json()
    assert all(item["latitude"] is not None for item in coords["items"])

    country = client.get("/api/map/events?days=7&precision=country").json()
    assert country["items"]
    assert all(item["location_precision"] == "country" for item in country["items"])
    # The shading payload groups country-only events per country.
    assert {row["country_code"] for row in country["country_shading"]} <= {"LK", "BR"}


def test_map_layer_rejects_unknown_precision(client, seeded):
    assert client.get("/api/map/events?precision=guessed").status_code == 422


def test_ingestion_status_reports_lock_state(client):
    body = client.get("/api/ingestion/status").json()
    assert body["running"] is False
    assert isinstance(body["enabled_providers"], list)
    assert isinstance(body["recent_runs"], list)


def test_round_is_null_safe_on_empty_aggregates(client):
    """Aggregates over empty tables must return null, never a 500.

    SQLite's own ``round(NULL, 2)`` behaviour varies by build; the connection
    registers a NULL-safe implementation so this is stable everywhere.
    """
    for path in ["/api/statistics/overview", "/api/countries?days=30", "/api/dashboard/overview"]:
        response = client.get(path)
        assert response.status_code == 200, path

    payload = client.get("/api/statistics/overview").json()
    assert payload["total_events"] == 0
    assert payload["categories"] == []
    assert payload["category_breakdown"] == []
    assert payload["timeline"] == []


def test_country_risk_on_empty_country_returns_null_averages(client):
    body = client.get("/api/countries/JP/risk").json()
    assert body["total_events"] == 0
    assert all(dimension["average_severity"] is None for dimension in body["dimensions"])
    assert body["coverage"]["level"] == "none"
