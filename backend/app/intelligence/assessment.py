"""Event assessment assembly: severity, confidence, priority, lifecycle.

One module owns the composition so the API, ingestion, alerts and the assistant
all read the same numbers from the same methodology.  Every part of the returned
payload is explainable: components, evidence and missing evidence travel with
the score into the event row and out through the API.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .clustering import derive_event_state
from .confidence import assess_confidence
from .normalize_time import parse_timestamp, to_utc_iso
from .geolocation import extract_location
from .priority import assess_priority
from .severity import assess_severity
from .verification import corroboration_description, determine_corroboration_level

logger = logging.getLogger(__name__)

OFFICIAL_DOMAIN_MARKERS = (
    "usgs", "who", "reliefweb", "gdacs", "noaa", "nws", "metoffice",
    "fema", "un.org", "unhcr", "ocha", "gov", "europa.eu",
)


def is_official_source(article: dict) -> bool:
    domain = (article.get("publisher_domain") or article.get("source") or "").lower()
    return any(marker in domain for marker in OFFICIAL_DOMAIN_MARKERS)


def record_timeline_entry(
    conn,
    event_id: int,
    occurred_at: str | None,
    change_type: str,
    description: str,
    article_id: int | None = None,
    confidence: float | None = None,
) -> None:
    """Append to the event's development timeline.

    Timeline entries are what let the UI separate *new information* from
    repeated reporting: a new article is only an entry when it changes
    something.
    """
    if not occurred_at:
        occurred_at = to_utc_iso(datetime.now(timezone.utc))
    conn.execute(
        """
        INSERT INTO event_timeline (
            event_id, occurred_at, change_type, description, article_id, confidence
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, occurred_at, change_type, description[:500], article_id, confidence),
    )


def _load_attributes(event: dict) -> dict:
    raw = event.get("data_sources")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def build_event_assessment(
    *,
    event: dict,
    articles: list[dict],
    independence,
    reported_casualties: int | None = None,
    contradictions: int = 0,
) -> dict:
    attributes = _load_attributes(event)
    magnitude = attributes.get("magnitude")
    official_severity = attributes.get("official_severity") or attributes.get("alert_level")
    if not official_severity and attributes.get("is_official_alert"):
        official_severity = attributes.get("severity")

    country_codes = {a.get("country_code") for a in articles if a.get("country_code")}
    country_count = len(country_codes) or (1 if event.get("country_code") else None)

    severity = assess_severity(
        category=event.get("category"),
        subcategory=event.get("subcategory"),
        reported_casualties=reported_casualties,
        magnitude=float(magnitude) if isinstance(magnitude, (int, float)) else None,
        official_severity=official_severity,
        country_count=country_count,
        location_precision=event.get("location_precision"),
        article_count=len(articles),
        provider_severity=event.get("severity"),
    )

    is_structured = bool(event.get("is_structured_observation"))
    official_sources = sum(1 for a in articles if is_official_source(a))
    if is_structured and event.get("provider_keys"):
        official_sources += 1

    # A structured provider record (USGS, CAP, ACLED…) is itself an official
    # first-party source, so it counts as one independent confirmation.
    independent = independence.independent_publishers or (
        1 if is_structured else 0
    )
    confidence = assess_confidence(
        independent_publishers=independent,
        syndicated_publishers=independence.syndicated_publishers,
        total_articles=max(len(articles), 1 if is_structured else 0),
        reporting_types=[a.get("reporting_type") or "direct" for a in articles]
        or (["direct"] if is_structured else []),
        location_precision=event.get("location_precision") or "unknown",
        time_precision=event.get("occurred_at_precision") or "unknown",
        classification_confidence=event.get("classification_confidence"),
        official_sources=official_sources,
        contradictions=contradictions,
    )

    previous_reports = int(event.get("article_count") or 0)
    state, state_reason = derive_event_state(
        created_at=event.get("created_at"),
        last_seen_at=event.get("last_seen_at") or to_utc_iso(datetime.now(timezone.utc)),
        current_state=event.get("event_state"),
        report_count=len(articles) or 1,
        independent_publishers=independence.independent_publishers,
        recent_report_count=len(articles),
        previous_report_count=previous_reports,
        resolution_evidence=_has_resolution_evidence(articles),
    )

    priority = assess_priority(
        severity=severity["score"],
        confidence=confidence["score"],
        occurred_at=event.get("occurred_at") or event.get("event_time"),
        event_state=state,
        escalation_trend=event.get("escalation_trend"),
    )

    level = determine_corroboration_level(independent)

    confidence_explanation = {
        "summary": _confidence_sentence(confidence, level),
        "corroboration_level": level,
        "corroboration_description": corroboration_description(level),
        "independent_publishers": independent,
        "syndicated_publishers": independence.syndicated_publishers,
        "publisher_families": independence.publisher_families,
        "duplicate_pairs": independence.duplicate_pairs[:10],
        "limitations": _limitations(confidence, event),
        "state_reason": state_reason,
    }

    return {
        "severity": severity,
        "confidence": confidence,
        "priority": priority,
        "confidence_explanation": confidence_explanation,
        "corroboration_level": level,
        "state": state,
        "importance": _importance_from_severity(severity["score"]),
    }


def _confidence_sentence(confidence: dict, level: str) -> str:
    score = confidence.get("score")
    if score is None:
        return "No corroborating evidence is available for this event."
    percent = round(score * 100)
    return (
        f"Intelligence confidence is {percent}% ({corroboration_description(level)})"
    )


def _limitations(confidence: dict, event: dict) -> list[str]:
    limitations = []
    missing = confidence.get("missing_evidence") or []
    friendly = {
        "independent_corroboration": "Only one publisher could be confirmed.",
        "source_diversity": "Supporting article diversity is unknown.",
        "reporting_directness": "It is not clear whether reporting is first-hand.",
        "location_precision": "The incident location is only known at country level.",
        "time_precision": "The incident time is approximate or unknown.",
        "classification_certainty": "The event category is uncertain.",
    }
    for key in missing:
        if key in friendly:
            limitations.append(friendly[key])
    if (event.get("location_precision") or "unknown") in {"country", "unknown"}:
        limitations.append(
            "Coordinates are not displayed because the exact location is not supported by evidence."
        )
    return limitations


def _has_resolution_evidence(articles: list[dict]) -> bool:
    markers = (
        "all clear", "all-clear", "recovery complete", "state of emergency lifted",
        "ceasefire holds", "peace agreement signed", "outbreak declared over",
        "ended the outbreak", "fire contained", "fire fully contained",
    )
    text = " ".join(
        f"{a.get('title') or ''} {a.get('description') or ''}".lower() for a in articles
    )
    return any(marker in text for marker in markers)


def _importance_from_severity(score: float | None) -> int:
    if score is None:
        return 5
    return max(1, min(10, round(score)))


def enrich_location_from_text(event: dict, text: str) -> dict:
    """Promote a country-level event to city level when the text names a city.

    Never invents coordinates: a promotion only happens when a known city name
    appears and a coordinate for that city exists in the registry.
    """
    current = (event.get("location_precision") or "unknown")
    if current in {"exact", "city"}:
        return {}

    location = extract_location(text, fallback_country_code=event.get("country_code"))
    if location.precision in {"city", "approximate"} and location.latitude is not None:
        return {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "location_precision": location.precision,
            "location_text": location.location_text,
            "geocoding_source": location.source,
            "geocoding_confidence": location.confidence,
        }
    return {}


def assessment_payload_for_event(conn, event_id: int) -> dict:
    """Read the persisted assessment and attach its evidence."""
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        return {}
    event = dict(event)
    try:
        severity = json.loads(event["severity_components"]) if event.get("severity_components") else None
    except (TypeError, ValueError):
        severity = None
    try:
        confidence = json.loads(event["confidence_components"]) if event.get("confidence_components") else None
    except (TypeError, ValueError):
        confidence = None
    try:
        explanation = json.loads(event["confidence_explanation"]) if event.get("confidence_explanation") else None
    except (TypeError, ValueError):
        explanation = None

    return {
        "severity": severity,
        "confidence": confidence,
        "confidence_explanation": explanation,
        "priority": {
            "score": event.get("priority_score"),
            "label": event.get("priority_label"),
        },
        "corroboration_level": event.get("corroboration_level"),
        "event_state": event.get("event_state"),
        "assessment_updated_at": event.get("assessment_updated_at"),
        "last_recalculation": parse_timestamp(event.get("assessment_updated_at")),
    }
