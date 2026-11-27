"""Intelligence aggregation API.

Serves the data the workspace needs, computed from stored records only:

* ``/api/dashboard/overview``      live operational picture
* ``/api/providers``               provider health + ingestion history
* ``/api/taxonomy``                the versioned taxonomy
* ``/api/search``                  unified search across events/entities/countries
* ``/api/countries/{code}/risk``   explainable country indicators
* ``/api/anomalies``               emerging-event detection
* ``/api/entities``                entity intelligence
* ``/api/alerts``                  alert centre
* ``/api/reports``                 report generation/export
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..database.db import get_connection, write_connection
from ..intelligence.taxonomy import (
    TAXONOMY,
    TAXONOMY_VERSION,
    category_label,
    taxonomy_payload,
)
from ..intelligence.geolocation import COUNTRY_BY_CODE, coordinate_for_country
from .auth import get_optional_user

router = APIRouter(prefix="/api", tags=["intelligence"])


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
@router.get("/dashboard/overview")
def dashboard_overview(hours: int = Query(24, ge=1, le=168)):
    """One query set that powers the overview dashboard.

    Everything here is counted from the database; nothing is estimated or
    hardcoded. Freshness fields let the UI show how old the picture is.
    """
    now = datetime.now(timezone.utc)
    window_start = _iso(now - timedelta(hours=hours))
    day_start = _iso(now - timedelta(hours=24))

    conn = get_connection()
    try:
        def scalar(sql: str, params=()):
            return conn.execute(sql, params).fetchone()[0]

        totals = {
            "events": scalar("SELECT COUNT(*) FROM events"),
            "active_events": scalar(
                "SELECT COUNT(*) FROM events WHERE event_state NOT IN ('resolved','archived')"
            ),
            "critical_events": scalar("SELECT COUNT(*) FROM events WHERE severity >= 8.5"),
            "high_events": scalar("SELECT COUNT(*) FROM events WHERE severity >= 6.5"),
            "developing_events": scalar(
                "SELECT COUNT(*) FROM events WHERE event_state IN ('developing','escalating')"
            ),
            "countries_affected": scalar(
                "SELECT COUNT(DISTINCT country_code) FROM events WHERE country_code IS NOT NULL"
            ),
            "events_24h": scalar(
                "SELECT COUNT(*) FROM events WHERE julianday(COALESCE(occurred_at,event_time,created_at)) >= julianday(?)",
                (day_start,),
            ),
            "high_confidence_events": scalar(
                "SELECT COUNT(*) FROM events WHERE confidence >= 0.75"
            ),
            "active_alerts": scalar("SELECT COUNT(*) FROM alerts WHERE status = 'new'"),
            "articles": scalar("SELECT COUNT(*) FROM articles"),
            "last_event_at": scalar(
                "SELECT MAX(COALESCE(last_seen_at, updated_at)) FROM events"
            ),
            "latest_ingestion": scalar(
                "SELECT MAX(finished_at) FROM collection_runs WHERE status IN ('healthy','degraded')"
            ),
        }

        severity_distribution = [
            {"label": "critical", "count": scalar("SELECT COUNT(*) FROM events WHERE severity >= 8.5")},
            {"label": "high", "count": scalar("SELECT COUNT(*) FROM events WHERE severity >= 6.5 AND severity < 8.5")},
            {"label": "moderate", "count": scalar("SELECT COUNT(*) FROM events WHERE severity >= 4.5 AND severity < 6.5")},
            {"label": "low", "count": scalar("SELECT COUNT(*) FROM events WHERE severity >= 2.5 AND severity < 4.5")},
            {"label": "minimal", "count": scalar("SELECT COUNT(*) FROM events WHERE severity IS NOT NULL AND severity < 2.5")},
            {"label": "unknown", "count": scalar("SELECT COUNT(*) FROM events WHERE severity IS NULL")},
        ]

        categories = [
            dict(row)
            for row in conn.execute(
                """
                SELECT category, COUNT(*) AS count,
                       SUM(CASE WHEN severity >= 8.5 THEN 1 ELSE 0 END) AS critical,
                       ROUND(AVG(severity), 2) AS average_severity
                FROM events
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
                """
            ).fetchall()
        ]

        countries = [
            dict(row)
            for row in conn.execute(
                """
                SELECT country, country_code, COUNT(*) AS event_count,
                       MAX(severity) AS max_severity,
                       ROUND(AVG(confidence), 2) AS average_confidence,
                       SUM(CASE WHEN event_state IN ('developing','escalating') THEN 1 ELSE 0 END) AS developing
                FROM events
                WHERE country_code IS NOT NULL
                GROUP BY country_code
                ORDER BY event_count DESC
                LIMIT 12
                """
            ).fetchall()
        ]

        activity = [
            dict(row)
            for row in conn.execute(
                """
                SELECT substr(COALESCE(occurred_at, event_time, created_at), 1, 13) AS hour,
                       COUNT(*) AS events,
                       SUM(CASE WHEN severity >= 6.5 THEN 1 ELSE 0 END) AS high_severity
                FROM events
                WHERE julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
                GROUP BY hour
                ORDER BY hour ASC
                """,
                (window_start,),
            ).fetchall()
        ]

        states = [
            dict(row)
            for row in conn.execute(
                "SELECT event_state AS state, COUNT(*) AS count FROM events GROUP BY event_state"
            ).fetchall()
        ]

        source_mix = [
            dict(row)
            for row in conn.execute(
                """
                SELECT provider, COUNT(*) AS articles,
                       COUNT(DISTINCT publisher_domain) AS publishers
                FROM articles
                WHERE provider IS NOT NULL
                GROUP BY provider
                ORDER BY articles DESC
                """
            ).fetchall()
        ]

        important = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, category, subcategory, country, country_code,
                       latitude, longitude, location_precision, severity, severity_label,
                       confidence, priority_score, priority_label, event_state,
                       occurred_at, corroboration_level, independent_source_count
                FROM events
                WHERE julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
                  AND severity IS NOT NULL
                ORDER BY COALESCE(priority_score, 0) DESC, severity DESC
                LIMIT 10
                """,
                (window_start,),
            ).fetchall()
        ]

        recent_feed = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, category, subcategory, country, country_code,
                       latitude, longitude, location_precision, severity, severity_label,
                       confidence, event_state, occurred_at, priority_score
                FROM events
                ORDER BY COALESCE(occurred_at, event_time, created_at) DESC, id DESC
                LIMIT 25
                """
            ).fetchall()
        ]

        coverage = {
            "events_with_coordinates": scalar(
                "SELECT COUNT(*) FROM events WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ),
            "events_country_only": scalar(
                "SELECT COUNT(*) FROM events WHERE location_precision = 'country'"
            ),
            "events_unknown_location": scalar(
                "SELECT COUNT(*) FROM events WHERE location_precision = 'unknown' OR location_precision IS NULL"
            ),
            "earliest_event_at": scalar(
                "SELECT MIN(COALESCE(occurred_at, event_time, created_at)) FROM events"
            ),
            "latest_event_at": totals["last_event_at"],
        }
    finally:
        conn.close()

    from ..ingestion.registry import provider_status_summary

    return {
        "generated_at": _iso(now),
        "window_hours": hours,
        "taxonomy_version": TAXONOMY_VERSION,
        "totals": totals,
        "severity_distribution": severity_distribution,
        "categories": categories,
        "countries": countries,
        "activity": activity,
        "event_states": states,
        "source_mix": source_mix,
        "important_events": important,
        "recent_events": recent_feed,
        "coverage": coverage,
        "providers": provider_status_summary(),
        "freshness": {
            "latest_ingestion": totals["latest_ingestion"],
            "latest_event": totals["last_event_at"],
        },
    }


# ----------------------------------------------------------------------
# Providers
# ----------------------------------------------------------------------
@router.get("/providers")
def providers(history: bool = False):
    from ..ingestion.registry import provider_health_payload

    items = provider_health_payload(include_history=history)
    summary: dict[str, int] = {}
    for item in items:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    return {"items": items, "by_status": summary, "count": len(items)}


@router.get("/providers/history")
def provider_history(
    provider: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    from ..ingestion.registry import collection_history

    return {"items": collection_history(provider_key=provider, limit=limit)}


@router.get("/taxonomy")
def taxonomy():
    return taxonomy_payload()


# ----------------------------------------------------------------------
# Unified search
# ----------------------------------------------------------------------
@router.get("/search")
def unified_search(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(get_optional_user),
):
    """Search events, entities and countries with one query."""
    like = f"%{q}%"
    conn = get_connection()
    try:
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, category, country_code, severity, confidence,
                       COALESCE(occurred_at, event_time) AS occurred_at
                FROM events
                WHERE title LIKE ? OR summary LIKE ?
                ORDER BY COALESCE(priority_score, 0) DESC, COALESCE(occurred_at, event_time) DESC
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        ]
        entities = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, name, entity_type, country_code, mention_count
                FROM entities
                WHERE name LIKE ? OR normalized_name LIKE ?
                ORDER BY mention_count DESC
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        ]
        countries = [
            {"country_code": entry["code"], "country": entry["name"]}
            for entry in COUNTRY_BY_CODE.values()
            if q.lower() in entry["name"].lower() or q.upper() == entry["code"]
        ][:limit]
        articles = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, url, publisher, published_at
                FROM articles
                WHERE title LIKE ?
                ORDER BY COALESCE(published_at, first_seen_at) DESC
                LIMIT ?
                """,
                (like, limit),
            ).fetchall()
        ]
    finally:
        conn.close()

    return {
        "query": q,
        "events": events,
        "entities": entities,
        "countries": countries,
        "articles": articles,
        "total": len(events) + len(entities) + len(countries) + len(articles),
    }


# ----------------------------------------------------------------------
# Country intelligence
# ----------------------------------------------------------------------
COUNTRY_DIMENSIONS = {
    "conflict_security": ("armed_conflict", "terrorism_extremism"),
    "political_instability": ("political_development", "protest_unrest"),
    "civil_unrest": ("protest_unrest",),
    "natural_disasters": ("natural_disaster",),
    "public_health": ("public_health",),
    "humanitarian": ("humanitarian",),
    "economic": ("economic_financial",),
    "energy_infrastructure": ("energy_infrastructure", "transportation"),
    "environment": ("environmental", "severe_weather"),
}


@router.get("/countries/{country_code}/risk")
def country_risk(
    country_code: str,
    days: int = Query(30, ge=1, le=365),
):
    """Explainable country indicators.

    Deliberately *not* a single "risk score". Each dimension is reported with
    its input events, its own coverage caveat and the reporting volume that
    supports it, because a country with little coverage must not look safe.
    """
    code = country_code.upper()
    if code not in COUNTRY_BY_CODE:
        raise HTTPException(status_code=404, detail="Unknown country code")

    since = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    conn = get_connection()
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, category, subcategory, severity, severity_label,
                       confidence, event_state, occurred_at, priority_score
                FROM events
                WHERE country_code = ?
                  AND julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
                ORDER BY COALESCE(occurred_at, event_time) DESC
                """,
                (code, since),
            ).fetchall()
        ]
        article_count = conn.execute(
            """
            SELECT COUNT(*) FROM articles a
            JOIN event_articles ea ON ea.article_id = a.id
            JOIN events e ON e.id = ea.event_id
            WHERE e.country_code = ?
              AND julianday(COALESCE(e.occurred_at, e.event_time, e.created_at)) >= julianday(?)
            """,
            (code, since),
        ).fetchone()[0]
        publisher_count = conn.execute(
            """
            SELECT COUNT(DISTINCT a.publisher_domain) FROM articles a
            JOIN event_articles ea ON ea.article_id = a.id
            JOIN events e ON e.id = ea.event_id
            WHERE e.country_code = ?
            """,
            (code,),
        ).fetchone()[0]

        # Movement: fixed 24h / 7d windows against the immediately preceding
        # equal windows, independent of the selected period, so "rising" and
        # "falling" always mean the same comparison. Counts of stored events
        # only - a fall can mean less reporting, not a calmer country.
        now_dt = datetime.now(timezone.utc)

        def count_between(start_iso: str, end_iso: str | None = None) -> int:
            sql = (
                "SELECT COUNT(*) FROM events WHERE country_code = ? "
                "AND julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)"
            )
            window_params: list = [code, start_iso]
            if end_iso is not None:
                sql += (
                    " AND julianday(COALESCE(occurred_at, event_time, created_at)) < julianday(?)"
                )
                window_params.append(end_iso)
            return conn.execute(sql, window_params).fetchone()[0]

        movement = {
            "events_24h": count_between(_iso(now_dt - timedelta(hours=24))),
            "events_previous_24h": count_between(
                _iso(now_dt - timedelta(hours=48)), _iso(now_dt - timedelta(hours=24))
            ),
            "events_7d": count_between(_iso(now_dt - timedelta(days=7))),
            "events_previous_7d": count_between(
                _iso(now_dt - timedelta(days=14)), _iso(now_dt - timedelta(days=7))
            ),
        }

        # Seven-day daily activity by taxonomy category. The frontend groups
        # categories into map layers for the lane display; the API stays at
        # category granularity so no grouping decision is baked in twice.
        timeline_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT substr(COALESCE(occurred_at, event_time, created_at), 1, 10) AS day,
                       category, COUNT(*) AS events, MAX(severity) AS max_severity
                FROM events
                WHERE country_code = ?
                  AND julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
                GROUP BY day, category
                """,
                (code, _iso(now_dt - timedelta(days=7))),
            ).fetchall()
        ]
    finally:
        conn.close()

    by_day: dict[str, dict] = {}
    for row in timeline_rows:
        day = by_day.setdefault(
            row["day"], {"date": row["day"], "total": 0, "max_severity": None, "by_category": {}}
        )
        day["total"] += row["events"]
        if row["max_severity"] is not None:
            day["max_severity"] = (
                row["max_severity"]
                if day["max_severity"] is None
                else max(day["max_severity"], row["max_severity"])
            )
        if row["category"]:
            day["by_category"][row["category"]] = {
                "events": row["events"],
                "max_severity": row["max_severity"],
            }
    timeline_days = []
    for offset in range(6, -1, -1):
        date_key = (now_dt - timedelta(days=offset)).strftime("%Y-%m-%d")
        timeline_days.append(
            by_day.get(
                date_key,
                {"date": date_key, "total": 0, "max_severity": None, "by_category": {}},
            )
        )

    # Active signals: the reporting categories actually present in the
    # selected period, ranked by their worst severity. Absence of a signal
    # means nothing was collected in that category - not that it is quiet.
    signal_map: dict[str, dict] = {}
    for row in rows:
        category = row.get("category")
        if not category:
            continue
        signal = signal_map.setdefault(
            category,
            {
                "category": category,
                "label": category_label(category),
                "event_count": 0,
                "max_severity": None,
                "latest_at": None,
            },
        )
        signal["event_count"] += 1
        if row.get("severity") is not None:
            signal["max_severity"] = (
                row["severity"]
                if signal["max_severity"] is None
                else max(signal["max_severity"], row["severity"])
            )
        occurred = row.get("occurred_at")
        if occurred and (signal["latest_at"] is None or occurred > signal["latest_at"]):
            signal["latest_at"] = occurred
    active_signals = sorted(
        signal_map.values(),
        key=lambda s: (s["max_severity"] or 0, s["event_count"]),
        reverse=True,
    )[:8]

    dimensions = []
    for name, categories in COUNTRY_DIMENSIONS.items():
        subset = [row for row in rows if row["category"] in categories]
        severities = [row["severity"] for row in subset if row["severity"] is not None]
        dimensions.append(
            {
                "dimension": name,
                "event_count": len(subset),
                "average_severity": round(sum(severities) / len(severities), 2) if severities else None,
                "max_severity": max(severities) if severities else None,
                "developing_events": sum(
                    1 for row in subset if row["event_state"] in {"developing", "escalating"}
                ),
                "categories": list(categories),
                "input_event_ids": [row["id"] for row in subset[:10]],
                "coverage": "no_events" if not subset else "observed",
            }
        )

    # Coverage caveat: reporting volume is the honest denominator.
    if article_count == 0:
        coverage_note = (
            "No reporting was collected for this country in the selected period. "
            "This does not indicate that conditions are safe."
        )
        coverage_level = "none"
    elif article_count < 5:
        coverage_note = (
            f"Only {article_count} article(s) from {publisher_count} publisher(s) were "
            "collected. Indicator comparisons are unreliable at this coverage level."
        )
        coverage_level = "sparse"
    elif article_count < 25:
        coverage_note = (
            f"{article_count} articles from {publisher_count} publishers provide partial coverage."
        )
        coverage_level = "partial"
    else:
        coverage_note = (
            f"{article_count} articles from {publisher_count} publishers provide reasonable coverage."
        )
        coverage_level = "good"

    return {
        "country_code": code,
        "country": COUNTRY_BY_CODE[code]["name"],
        "period_days": days,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "total_events": len(rows),
        "articles": article_count,
        "publishers": publisher_count,
        "coverage": {"level": coverage_level, "note": coverage_note},
        "dimensions": dimensions,
        "movement": movement,
        "timeline": {"window_days": 7, "days": timeline_days},
        "active_signals": active_signals,
        "recent_events": rows[:20],
        "methodology": (
            "Indicators are counts and severity averages of stored events within the "
            "period, grouped by taxonomy category. They are descriptive statistics over "
            "collected reporting, not an empirical risk index, and they inherit the "
            "collection coverage shown above."
        ),
        "limitations": [
            "Countries with less collected reporting will show fewer events regardless of the real situation.",
            "Severity is derived from reported impact, which itself depends on how well a region is covered by media.",
            "No forecasting or prediction is implied by these indicators.",
        ],
    }


@router.get("/countries")
def countries_summary(days: int = Query(30, ge=1, le=365)):
    since = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    conn = get_connection()
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT country_code, country, COUNT(*) AS event_count,
                       MAX(severity) AS max_severity,
                       ROUND(AVG(severity), 2) AS average_severity,
                       SUM(CASE WHEN event_state IN ('developing','escalating') THEN 1 ELSE 0 END) AS developing
                FROM events
                WHERE country_code IS NOT NULL
                  AND julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
                GROUP BY country_code
                ORDER BY event_count DESC
                """,
                (since,),
            ).fetchall()
        ]
        # Fixed-window trend (last 24h, last 7d vs the previous 7d), computed
        # over the same fixed windows for every country regardless of the
        # selected period so rows stay comparable.
        trend_by_code = {
            row["country_code"]: dict(row)
            for row in conn.execute(
                """
                SELECT country_code,
                       SUM(CASE WHEN julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday('now', '-24 hours') THEN 1 ELSE 0 END) AS events_24h,
                       SUM(CASE WHEN julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday('now', '-7 days') THEN 1 ELSE 0 END) AS events_7d,
                       SUM(CASE WHEN julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday('now', '-14 days')
                                 AND julianday(COALESCE(occurred_at, event_time, created_at)) < julianday('now', '-7 days') THEN 1 ELSE 0 END) AS events_previous_7d
                FROM events
                WHERE country_code IS NOT NULL
                GROUP BY country_code
                """
            ).fetchall()
        }
    finally:
        conn.close()
    for row in rows:
        raw_trend = trend_by_code.get(row["country_code"], {})
        trend = {
            key: raw_trend.get(key, 0) or 0
            for key in ("events_24h", "events_7d", "events_previous_7d")
        }
        if trend["events_7d"] > trend["events_previous_7d"]:
            direction = "rising"
        elif trend["events_7d"] < trend["events_previous_7d"]:
            direction = "falling"
        else:
            direction = "steady"
        row["trend"] = {**trend, "direction": direction}
    return {"items": rows, "count": len(rows), "period_days": days}


# ----------------------------------------------------------------------
# Anomalies
# ----------------------------------------------------------------------
@router.get("/anomalies")
def anomalies(limit: int = Query(50, ge=1, le=200), include_dismissed: bool = False):
    conn = get_connection()
    try:
        from ..intelligence.anomaly import detect_anomalies

        fresh = detect_anomalies(conn)
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT * FROM anomalies
                {'WHERE dismissed = 0' if not include_dismissed else ''}
                ORDER BY detected_at DESC, score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
    finally:
        conn.close()

    for row in rows:
        if isinstance(row.get("sample_event_ids"), str):
            try:
                row["sample_event_ids"] = json.loads(row["sample_event_ids"])
            except (TypeError, ValueError):
                row["sample_event_ids"] = []
    return {"items": rows, "newly_detected": fresh, "count": len(rows)}


@router.post("/anomalies/{anomaly_id}/dismiss", status_code=204)
def dismiss_anomaly(anomaly_id: int):
    with write_connection() as conn:
        cursor = conn.execute(
            "UPDATE anomalies SET dismissed = 1 WHERE id = ?", (anomaly_id,)
        )
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="Anomaly not found")


# ----------------------------------------------------------------------
# Entities
# ----------------------------------------------------------------------
@router.get("/entities")
def entity_list(
    entity_type: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    conditions, params = [], []
    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if q:
        conditions.append("(name LIKE ? OR description LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = get_connection()
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT * FROM entities {where}
                ORDER BY mention_count DESC, name ASC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        ]
    finally:
        conn.close()
    return {"items": rows, "count": len(rows)}


@router.get("/entities/{entity_id}")
def entity_detail(entity_id: int):
    conn = get_connection()
    try:
        entity = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT e.id, e.title, e.category, e.country_code, e.severity,
                       COALESCE(e.occurred_at, e.event_time) AS occurred_at, m.role
                FROM event_entity_mentions m
                JOIN events e ON e.id = m.event_id
                WHERE m.entity_id = ?
                ORDER BY COALESCE(e.occurred_at, e.event_time) DESC
                LIMIT 50
                """,
                (entity_id,),
            ).fetchall()
        ]
        aliases = [
            row["alias"]
            for row in conn.execute(
                "SELECT alias FROM entity_aliases WHERE entity_id = ?", (entity_id,)
            ).fetchall()
        ]
        relationships = [
            dict(row)
            for row in conn.execute(
                """
                SELECT r.relationship, r.confidence, r.evidence,
                       en.id AS entity_id, en.name, en.entity_type
                FROM entity_relationships r
                JOIN entities en ON en.id = CASE
                    WHEN r.source_entity_id = ? THEN r.target_entity_id
                    ELSE r.source_entity_id END
                WHERE r.source_entity_id = ? OR r.target_entity_id = ?
                """,
                (entity_id, entity_id, entity_id),
            ).fetchall()
        ]
    finally:
        conn.close()
    return {**dict(entity), "aliases": aliases, "events": events, "relationships": relationships}


# ----------------------------------------------------------------------
# Alerts
# ----------------------------------------------------------------------
class AlertRuleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    enabled: bool = True
    country_code: str | None = None
    category: str | None = None
    subcategory: str | None = None
    min_severity: float | None = Field(None, ge=0, le=10)
    min_confidence: float | None = Field(None, ge=0, le=1)
    min_magnitude: float | None = Field(None, ge=0, le=10)
    event_state: str | None = None
    entity: str | None = None
    keywords: str | None = None


@router.get("/alerts")
def alerts(
    status: str | None = Query(None, pattern="^(new|acknowledged|resolved|dismissed)$"),
    limit: int = Query(100, ge=1, le=300),
    user=Depends(get_optional_user),
):
    condition = "WHERE a.status = ?" if status else ""
    params = ([status] if status else []) + [limit]
    conn = get_connection()
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT a.*, e.title AS event_title, e.category, e.country_code,
                       e.severity AS event_severity, e.confidence AS event_confidence,
                       COALESCE(e.occurred_at, e.event_time) AS occurred_at,
                       r.name AS rule_name
                FROM alerts a
                LEFT JOIN events e ON e.id = a.event_id
                LEFT JOIN alert_rules r ON r.id = a.rule_id
                {condition}
                ORDER BY a.triggered_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        ]
        counts = {
            row["status"]: row["count"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count FROM alerts GROUP BY status"
            ).fetchall()
        }
    finally:
        conn.close()

    for row in rows:
        if isinstance(row.get("evidence"), str):
            try:
                row["evidence"] = json.loads(row["evidence"])
            except (TypeError, ValueError):
                pass
    return {"items": rows, "by_status": counts}


@router.post("/alerts/{alert_id}/status", status_code=200)
def update_alert_status(
    alert_id: int,
    payload: dict = Body(...),
    user=Depends(get_optional_user),
):
    status = payload.get("status")
    if status not in {"new", "acknowledged", "resolved", "dismissed"}:
        raise HTTPException(status_code=422, detail="Invalid alert status")
    now = _iso(datetime.now(timezone.utc))
    with write_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE alerts SET status = ?,
                acknowledged_at = CASE WHEN ? = 'acknowledged' THEN ? ELSE acknowledged_at END,
                resolved_at = CASE WHEN ? IN ('resolved','dismissed') THEN ? ELSE resolved_at END
            WHERE id = ?
            """,
            (status, status, now, status, now, alert_id),
        )
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"id": alert_id, "status": status}


@router.get("/alert-rules")
def alert_rules(user=Depends(get_optional_user)):
    conn = get_connection()
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM alert_rules ORDER BY id").fetchall()]
    finally:
        conn.close()
    return {"items": rows}


@router.post("/alert-rules", status_code=201)
def create_alert_rule(payload: AlertRuleRequest, user=Depends(get_optional_user)):
    with write_connection() as conn:
        rule_id = conn.execute(
            """
            INSERT INTO alert_rules (
                user_id, name, enabled, country_code, category, subcategory,
                min_severity, min_confidence, min_magnitude, event_state, entity, keywords
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"] if user else None,
                payload.name,
                1 if payload.enabled else 0,
                payload.country_code.upper() if payload.country_code else None,
                payload.category,
                payload.subcategory,
                payload.min_severity,
                payload.min_confidence,
                payload.min_magnitude,
                payload.event_state,
                payload.entity,
                payload.keywords,
            ),
        ).lastrowid
    return {"id": rule_id, **payload.model_dump()}


@router.delete("/alert-rules/{rule_id}", status_code=204)
def delete_alert_rule(rule_id: int, user=Depends(get_optional_user)):
    with write_connection() as conn:
        cursor = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="Alert rule not found")


# ----------------------------------------------------------------------
# Saved searches / watchlists
# ----------------------------------------------------------------------
@router.get("/saved-searches")
def saved_searches(user=Depends(get_optional_user)):
    conn = get_connection()
    try:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM saved_searches ORDER BY COALESCE(last_used_at, created_at) DESC"
        ).fetchall()]
    finally:
        conn.close()
    for row in rows:
        if isinstance(row.get("filters"), str):
            try:
                row["filters"] = json.loads(row["filters"])
            except (TypeError, ValueError):
                pass
    return {"items": rows}


@router.post("/saved-searches", status_code=201)
def create_saved_search(payload: dict = Body(...), user=Depends(get_optional_user)):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A name is required")
    with write_connection() as conn:
        search_id = conn.execute(
            "INSERT INTO saved_searches (user_id, name, query, filters) VALUES (?, ?, ?, ?)",
            (
                user["id"] if user else None,
                name[:120],
                str(payload.get("query") or "")[:300],
                json.dumps(payload.get("filters") or {}),
            ),
        ).lastrowid
    return {"id": search_id, "name": name}


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: int, user=Depends(get_optional_user)):
    with write_connection() as conn:
        cursor = conn.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="Saved search not found")


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------
@router.post("/reports")
def generate_report(payload: dict = Body(...), user=Depends(get_optional_user)):
    from ..reports.builder import build_report

    scope = str(payload.get("scope") or "global")
    if scope not in {"global", "country", "category", "event", "anomaly"}:
        raise HTTPException(status_code=422, detail="Unsupported report scope")
    report = build_report(
        scope=scope,
        scope_value=payload.get("scope_value"),
        days=int(payload.get("days") or 7),
        include_ai=bool(payload.get("include_ai")),
    )
    return report


@router.get("/reports")
def list_reports(limit: int = Query(20, ge=1, le=100), user=Depends(get_optional_user)):
    conn = get_connection()
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT id, title, scope, scope_value, period_start, period_end, format, generated_at "
                "FROM reports ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        ]
    finally:
        conn.close()
    return {"items": rows}


@router.get("/system/status")
def system_status():
    """Operational status: database, migrations, scheduler, AI availability."""
    from ..database.migrations import verify_migrations
    from ..scheduler.runner import schedule_state

    db_status = {"available": False}
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
            db_status["available"] = True
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
            db_status["integrity"] = integrity
            db_status["migrations"] = verify_migrations(conn)
            from ..database.db import current_db_path

            active_db = current_db_path()
            db_status["path"] = str(active_db)
            db_status["size_bytes"] = active_db.stat().st_size if active_db.exists() else 0
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        db_status["error"] = type(exc).__name__

    return {
        "environment": settings.environment,
        "version": settings.app_version,
        "database": db_status,
        "scheduler": schedule_state(),
        "ai": {
            "ingestion_enabled": settings.ollama_enabled,
            "classification_enabled": settings.ai_classification_enabled,
            "rag_enabled": settings.rag_enabled,
        },
        "security": {
            "demo_data_enabled": settings.demo_data_enabled,
            "cors_origins": settings.cors_origin_list,
            "ssrf_private_hosts_allowed": settings.ssrf_allow_private_hosts,
        },
        "retention_days": settings.historical_retention_days,
    }


@router.get("/reports/{report_id}/export")
def export_report(
    report_id: int,
    format: str = Query("csv", pattern="^(csv|html)$"),
):
    from fastapi.responses import Response

    from ..reports.builder import build_report
    from ..reports.export import report_to_csv, report_to_html

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    report = json.loads(row["body"])
    report.setdefault("id", report_id)

    if format == "csv":
        return Response(
            content=report_to_csv(report),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="intelligence-report-{report_id}.csv"'
            },
        )
    return Response(
        content=report_to_html(report),
        media_type="text/html",
        headers={
            "Content-Disposition": f'inline; filename="intelligence-report-{report_id}.html"'
        },
    )


# ----------------------------------------------------------------------
# Map layer
# ----------------------------------------------------------------------
# "Major" on the map uses the platform's existing definitions, combined:
# high/critical severity bands (severity >= 6.5) or the statistics layer's
# major-event threshold (importance >= 8). Either signal qualifies, so an
# event with a legacy importance score but no severity assessment (or vice
# versa) is not silently dropped.
MAJOR_SEVERITY_THRESHOLD = 6.5
MAJOR_IMPORTANCE_THRESHOLD = 8
MAJOR_DEFINITION = (
    f"severity >= {MAJOR_SEVERITY_THRESHOLD} (high/critical) "
    f"or importance >= {MAJOR_IMPORTANCE_THRESHOLD}"
)


@router.get("/map/events")
def map_events(
    days: int = Query(7, ge=1, le=90),
    category: str | None = None,
    categories: str | None = Query(
        None,
        description="Comma-separated taxonomy categories (map layer filter).",
    ),
    country_code: str | None = None,
    min_severity: float | None = Query(None, ge=0, le=10),
    major_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=2000),
    precision: str = Query("all", pattern="^(all|coordinates|country)$"),
    user=Depends(get_optional_user),
):
    """Events for the map, with their location precision made explicit.

    The frontend must never plot a country-level event as a point: it would put
    a fabricated coordinate on the map. So each feature carries
    ``location_precision`` and the caller decides how to render it (region
    shading / list instead of a pin). Events without any location are excluded
    from this layer and reported in ``excluded`` so the count is honest.
    """
    since = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    conditions = [
        "julianday(COALESCE(e.occurred_at, e.event_time, e.created_at)) >= julianday(?)",
    ]
    params: list = [since]
    if category:
        conditions.append("e.category = ?")
        params.append(category)
    selected_categories: list[str] = []
    if categories is not None:
        selected_categories = [
            part.strip() for part in categories.split(",") if part.strip()
        ]
        unknown = [key for key in selected_categories if key not in TAXONOMY]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown categories: {', '.join(sorted(set(unknown)))}",
            )
        if selected_categories:
            placeholders = ", ".join("?" for _ in selected_categories)
            conditions.append(f"e.category IN ({placeholders})")
            params.extend(selected_categories)
        elif categories is not None:
            # The parameter was supplied but names no layer (every layer
            # toggled off): an explicit empty selection, not "no filter".
            conditions.append("1 = 0")
    if country_code:
        conditions.append("e.country_code = ?")
        params.append(country_code.upper())
    if min_severity is not None:
        conditions.append("e.severity >= ?")
        params.append(min_severity)
    if major_only:
        conditions.append(
            "(COALESCE(e.severity, 0) >= ? OR COALESCE(e.importance, 0) >= ?)"
        )
        params.extend([MAJOR_SEVERITY_THRESHOLD, MAJOR_IMPORTANCE_THRESHOLD])
    if precision == "coordinates":
        conditions.append("e.latitude IS NOT NULL AND e.longitude IS NOT NULL")
        conditions.append("e.location_precision IN ('exact','city','admin_region','region','locality','approximate')")
    elif precision == "country":
        conditions.append("e.location_precision = 'country'")

    where = " AND ".join(conditions)
    conn = get_connection()
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT e.id, e.title, e.category, e.subcategory, e.country,
                       e.country_code, e.latitude, e.longitude, e.location_precision,
                       e.location_text, e.severity, e.severity_label, e.confidence,
                       e.priority_score, e.priority_label, e.event_state, e.importance,
                       e.occurred_at, e.corroboration_level, e.independent_source_count,
                       e.is_structured_observation
                FROM events e
                WHERE {where}
                ORDER BY COALESCE(e.priority_score, 0) DESC,
                         COALESCE(e.severity, 0) DESC,
                         e.id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        ]
        # Coverage figures for the same window/filters, so the map legend can
        # say how many events it is *not* showing.
        base_where = " AND ".join(conditions)
        plotted = conn.execute(
            f"""
            SELECT COUNT(*) FROM events e WHERE {base_where}
              AND e.latitude IS NOT NULL AND e.longitude IS NOT NULL
              AND e.location_precision IN ('exact','city','admin_region','region','locality','approximate')
            """,
            params,
        ).fetchone()[0]
        country_only = conn.execute(
            f"SELECT COUNT(*) FROM events e WHERE {base_where} AND e.location_precision = 'country'",
            params,
        ).fetchone()[0]
        no_location = conn.execute(
            f"""
            SELECT COUNT(*) FROM events e WHERE {base_where}
              AND (e.location_precision IS NULL OR e.location_precision = 'unknown')
            """,
            params,
        ).fetchone()[0]

        # Country-level events are grouped per country so the UI can shade a
        # region instead of inventing a point.
        country_rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT e.country_code, e.country, COUNT(*) AS events,
                       MAX(e.severity) AS max_severity,
                       SUM(CASE WHEN e.severity >= 6.5 THEN 1 ELSE 0 END) AS high_severity
                FROM events e
                WHERE {base_where} AND e.country_code IS NOT NULL
                  AND e.location_precision = 'country'
                GROUP BY e.country_code
                """,
                params,
            ).fetchall()
        ]
        # Display anchor for each aggregate (country centroid from the local
        # registry). This is explicitly a *display anchor for an aggregate*,
        # never an event coordinate: `is_country_aggregate` tells the UI to
        # render it as a country bubble labelled with its event count, not
        # as an incident pin. Individual country-level events keep
        # latitude/longitude = None everywhere.
        for row in country_rows:
            anchor = coordinate_for_country(row.get("country_code"))
            row["latitude"] = anchor[0] if anchor else None
            row["longitude"] = anchor[1] if anchor else None
            row["is_country_aggregate"] = True

        # Per-category freshness for the map's layer panel. Computed over the
        # same window/scope but *without* the category and precision filters,
        # so a layer the user turned off still reports how fresh its data is
        # instead of pretending to be empty. Counts are stored events only.
        fresh_conditions = [
            "julianday(COALESCE(e.occurred_at, e.event_time, e.created_at)) >= julianday(?)",
        ]
        fresh_params: list = [since]
        if country_code:
            fresh_conditions.append("e.country_code = ?")
            fresh_params.append(country_code.upper())
        if min_severity is not None:
            fresh_conditions.append("e.severity >= ?")
            fresh_params.append(min_severity)
        if major_only:
            fresh_conditions.append(
                "(COALESCE(e.severity, 0) >= ? OR COALESCE(e.importance, 0) >= ?)"
            )
            fresh_params.extend([MAJOR_SEVERITY_THRESHOLD, MAJOR_IMPORTANCE_THRESHOLD])
        fresh_where = " AND ".join(fresh_conditions)
        category_freshness = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT e.category AS category, COUNT(*) AS events,
                       MAX(e.severity) AS max_severity,
                       MAX(COALESCE(e.last_seen_at, e.updated_at, e.occurred_at,
                                    e.event_time, e.created_at)) AS latest_event_at
                FROM events e
                WHERE {fresh_where} AND e.category IS NOT NULL
                GROUP BY e.category
                """,
                fresh_params,
            ).fetchall()
        ]
        latest_event_at = conn.execute(
            f"""
            SELECT MAX(COALESCE(e.last_seen_at, e.updated_at, e.occurred_at,
                                e.event_time, e.created_at))
            FROM events e WHERE {fresh_where}
            """,
            fresh_params,
        ).fetchone()[0]
        try:
            latest_ingestion_at = conn.execute(
                "SELECT MAX(finished_at) FROM collection_runs "
                "WHERE status IN ('healthy','degraded')"
            ).fetchone()[0]
        except Exception:  # noqa: BLE001 - freshness is advisory, never fatal
            latest_ingestion_at = None
    finally:
        conn.close()

    return {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "window_days": days,
        "major_only": major_only,
        "major_definition": MAJOR_DEFINITION if major_only else None,
        "precision_mode": precision,
        "categories": selected_categories,
        "items": rows,
        "country_shading": country_rows,
        "freshness": {
            "latest_event_at": latest_event_at,
            "latest_ingestion_at": latest_ingestion_at,
            "category_freshness": category_freshness,
            "note": (
                "Freshness describes stored data in this window only; a quiet "
                "layer means little was collected, not that nothing happened."
            ),
        },
        "coverage": {
            "returned": len(rows),
            "plotted_with_coordinates": plotted,
            "country_level_only": country_only,
            "no_location": no_location,
        },
        "legend": {
            "severity_bands": [
                {"label": "critical", "min": 8.5, "colour": "#ff5d7a"},
                {"label": "high", "min": 6.5, "colour": "#ff9f43"},
                {"label": "moderate", "min": 4.5, "colour": "#ffd166"},
                {"label": "low", "min": 2.5, "colour": "#36b8ff"},
                {"label": "minimal", "min": 0, "colour": "#7d93a8"},
            ],
            "note": (
                "Pins use coordinates reported by the source or resolved by the "
                "geocoder. Country-level events are shaded by country and never "
                "plotted as a point."
            ),
        },
    }
