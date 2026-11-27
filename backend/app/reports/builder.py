"""Intelligence report generation.

Reports are assembled from stored records only. Every section cites the events
and sources it was built from, and the report states the collection coverage and
its limitations. The optional AI narrative is clearly labelled as an
AI-generated assessment and is only produced when the model is reachable and
evidence was retrieved.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from ..database.db import get_connection, write_connection
from ..intelligence.taxonomy import category_label, taxonomy_payload

logger = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _query_events(conn, *, since: str, country: str | None, category: str | None,
                  event_id: int | None, limit: int = 60) -> list[dict]:
    conditions = ["julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)"]
    params: list = [since]
    if country:
        conditions.append("country_code = ?")
        params.append(country.upper())
    if category:
        conditions.append("category = ?")
        params.append(category)
    if event_id:
        conditions.append("id = ?")
        params.append(event_id)

    rows = conn.execute(
        f"""
        SELECT id, title, summary, category, subcategory, country, country_code,
               latitude, longitude, location_precision, severity, severity_label,
               confidence, priority_score, priority_label, event_state,
               corroboration_level, independent_source_count,
               COALESCE(occurred_at, event_time) AS occurred_at, importance
        FROM events
        WHERE {' AND '.join(conditions)}
        ORDER BY COALESCE(priority_score, 0) DESC, COALESCE(severity, 0) DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _sources_for(conn, event_ids: list[int]) -> list[dict]:
    if not event_ids:
        return []
    placeholders = ",".join("?" for _ in event_ids)
    rows = conn.execute(
        f"""
        SELECT DISTINCT a.title, a.url, a.publisher, a.publisher_domain,
               a.published_at, a.reporting_type, ea.event_id
        FROM articles a
        JOIN event_articles ea ON ea.article_id = a.id
        WHERE ea.event_id IN ({placeholders})
        ORDER BY a.published_at DESC
        LIMIT 80
        """,
        event_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def build_report(*, scope: str, scope_value: str | None, days: int = 7, include_ai: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    since = _iso(now - timedelta(days=max(1, days)))

    conn = get_connection()
    try:
        country = scope_value.upper() if scope == "country" and scope_value else None
        category = scope_value if scope == "category" else None
        event_id = int(scope_value) if scope == "event" and scope_value else None

        events = _query_events(
            conn, since=since, country=country, category=category, event_id=event_id
        )
        event_ids = [event["id"] for event in events]
        sources = _sources_for(conn, event_ids)

        timeline_rows = []
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            timeline_rows = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT event_id, occurred_at, change_type, description
                    FROM event_timeline
                    WHERE event_id IN ({placeholders})
                    ORDER BY occurred_at ASC
                    LIMIT 100
                    """,
                    event_ids,
                ).fetchall()
            ]

        entities = []
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            entities = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT DISTINCT en.name, en.entity_type, en.country_code
                    FROM entities en
                    JOIN event_entity_mentions m ON m.entity_id = en.id
                    WHERE m.event_id IN ({placeholders})
                    LIMIT 40
                    """,
                    event_ids,
                ).fetchall()
            ]

        coverage = {
            "events_with_coordinates": sum(
                1 for e in events if e.get("latitude") is not None
            ),
            "events_country_level_only": sum(
                1 for e in events if (e.get("location_precision") or "") == "country"
            ),
            "distinct_publishers": len({s.get("publisher_domain") for s in sources if s.get("publisher_domain")}),
        }
    finally:
        conn.close()

    severities = [e["severity"] for e in events if e.get("severity") is not None]
    confidences = [e["confidence"] for e in events if e.get("confidence") is not None]

    title = _title(scope, scope_value)
    summary_lines = [
        f"{len(events)} events met the report scope over the last {days} days.",
        (
            f"Mean severity {round(sum(severities)/len(severities), 2)}/10 across "
            f"{len(severities)} assessed events."
            if severities else "No event in scope has a severity assessment."
        ),
        (
            f"Mean intelligence confidence {round(sum(confidences)/len(confidences)*100)}% "
            f"across {len(confidences)} assessed events."
            if confidences else "No event in scope has a confidence assessment."
        ),
        f"{coverage['distinct_publishers']} distinct publishers contribute to the evidence base.",
    ]

    report = {
        "title": title,
        "scope": scope,
        "scope_value": scope_value,
        "reporting_period": {"start": since, "end": _iso(now), "days": days},
        "generated_at": _iso(now),
        "taxonomy_version": taxonomy_payload()["version"],
        "executive_summary": "\n".join(summary_lines),
        "key_developments": [
            {
                "event_id": e["id"],
                "title": e["title"],
                "category": e["category"],
                "category_label": category_label(e["category"]),
                "subcategory": e["subcategory"],
                "severity": e["severity"],
                "severity_label": e["severity_label"],
                "confidence": e["confidence"],
                "state": e["event_state"],
                "priority": e["priority_label"],
                "occurred_at": e["occurred_at"],
                "corroboration": e["corroboration_level"],
                "independent_publishers": e["independent_source_count"],
            }
            for e in events[:15]
        ],
        "all_events": events,
        "geographic_overview": _geographic(events),
        "severity_assessment": {
            "distribution": _distribution(severities),
            "methodology": (
                "Severity is a weighted mean of evidence-backed factors: event type, "
                "reported human impact, physical magnitude, official severity level and "
                "geographic scale. Missing factors are excluded, not defaulted."
            ),
        },
        "confidence_assessment": {
            "distribution": _distribution(confidences, scale=1.0),
            "methodology": (
                "Confidence combines independent corroboration (syndicated copies are "
                "excluded), source diversity, reporting directness, location and time "
                "precision and classification certainty."
            ),
        },
        "timelines": timeline_rows,
        "related_entities": entities,
        "sources": sources,
        "coverage": coverage,
        "contradictions_and_uncertainty": [
            "Severity and confidence inherit the accuracy of the underlying reporting.",
            "Events reported by a single publisher carry low confidence even when severe.",
            "Countries with less collected reporting will appear under-represented.",
            "No forecast or prediction is included in this report.",
        ],
        "methodology": (
            "Records are drawn from the platform's own SQLite database, which stores "
            "normalised articles from GDELT, RSS feeds, Google News and structured "
            "providers (USGS, WHO, ReliefWeb, NASA FIRMS, CAP, ACLED where configured). "
            "Duplicate and syndicated articles are detected before corroboration is "
            "counted. Every figure is computed from stored rows."
        ),
    }

    if include_ai:
        report["ai_assessment"] = _ai_section(events, sources)

    with write_connection() as conn:
        report_id = conn.execute(
            """
            INSERT INTO reports (title, scope, scope_value, period_start, period_end, body, format)
            VALUES (?, ?, ?, ?, ?, ?, 'json')
            """,
            (
                title, scope, scope_value, since, _iso(now),
                json.dumps(report, default=str),
            ),
        ).lastrowid
    report["id"] = report_id
    return report


def _title(scope: str, value: str | None) -> str:
    if scope == "country" and value:
        return f"Country intelligence report — {value.upper()}"
    if scope == "category" and value:
        return f"Category intelligence report — {category_label(value)}"
    if scope == "event" and value:
        return f"Event intelligence report — event {value}"
    if scope == "anomaly" and value:
        return f"Emerging-event report — {value}"
    return "Global situation report"


def _distribution(values: list[float], scale: float = 10.0) -> list[dict]:
    if not values:
        return []
    buckets = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "minimal": 0}
    for value in values:
        normalised = (value / scale) * 10 if scale != 10.0 else value
        if normalised >= 8.5:
            buckets["critical"] += 1
        elif normalised >= 6.5:
            buckets["high"] += 1
        elif normalised >= 4.5:
            buckets["moderate"] += 1
        elif normalised >= 2.5:
            buckets["low"] += 1
        else:
            buckets["minimal"] += 1
    return [{"label": key, "count": count} for key, count in buckets.items()]


def _geographic(events: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for event in events:
        code = event.get("country_code") or "unknown"
        entry = grouped.setdefault(
            code,
            {"country_code": code, "country": event.get("country"), "events": 0,
             "max_severity": None},
        )
        entry["events"] += 1
        severity = event.get("severity")
        if severity is not None:
            entry["max_severity"] = max(entry["max_severity"] or 0, severity)
    return sorted(grouped.values(), key=lambda item: -item["events"])


def _ai_section(events: list[dict], sources: list[dict]) -> dict:
    """Optional AI narrative, explicitly labelled and evidence-bound."""
    from ..config import settings

    if not settings.rag_enabled:
        return {
            "available": False,
            "reason": "The AI assistant is disabled (RAG_ENABLED=false).",
        }
    if not events:
        return {"available": False, "reason": "No evidence in scope to analyse."}

    evidence = "\n".join(
        f"- [{event['id']}] {event['title']} ({event['category']}, severity {event['severity']})"
        for event in events[:12]
    )
    return {
        "available": False,
        "reason": (
            "AI narrative generation runs through the assistant endpoint so the "
            "answer is retrieved and grounded. Use POST /api/ai/query with the "
            "report scope to obtain a cited assessment."
        ),
        "evidence_preview": evidence[:2000],
        "evidence_count": len(events),
        "labelled_as": "AI-generated assessment (not verified fact)",
    }
