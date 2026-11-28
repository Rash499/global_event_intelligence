"""Event query API.

Changes from the previous implementation:

* SSRF-safe image discovery (see ``security/ssrf.py``) instead of an unvalidated
  redirect-following fetch;
* the demo seed route is gated behind ``DEMO_DATA_ENABLED`` and refuses to run
  in production;
* cursor pagination plus filtering/sorting/search, so the frontend never has to
  download thousands of rows;
* event detail now carries provenance, precision, assessments and evidence.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..database.db import get_connection, write_connection
from ..database.queries import select_event, select_events
from ..security.ssrf import SsrfError, safe_fetch
from .auth import get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["events"])


class ImageMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta" or self.image_url:
            return
        values = {name.lower(): value for name, value in attrs}
        image_name = values.get("property", values.get("name", "")).lower()
        if image_name in {"og:image", "twitter:image", "og:image:url"}:
            self.image_url = values.get("content")


async def discover_image_url(url: str) -> str | None:
    """Fetch an article page safely and read its social image metadata."""
    try:
        result = await safe_fetch(url)
    except SsrfError as exc:
        logger.info("Skipping image discovery for %s: %s", url, exc)
        return None

    parser = ImageMetaParser()
    try:
        parser.feed(result.text[:1_000_000])
    except Exception:  # noqa: BLE001 - malformed HTML must not 500 the request
        return None

    if not parser.image_url:
        return None
    return urljoin(result.final_url, parser.image_url)


def _encode_cursor(row: dict, sort: str = "recent") -> str:
    if sort == "recent":
        key = row.get("occurred_at") or row.get("event_time") or row.get("created_at") or ""
    elif sort == "severity":
        key = row.get("severity") or 0
    elif sort == "priority":
        key = row.get("priority_score") or 0
    else:
        key = row.get("confidence") or 0
    payload = {"t": key, "i": row.get("id")}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str | None) -> tuple[str | float, int] | None:
    if not cursor:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        value = payload.get("t")
        if isinstance(value, (int, float)):
            return float(value), int(payload.get("i") or 0)
        return str(value or ""), int(payload.get("i") or 0)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid cursor")


def _serialize_event(row: dict) -> dict:
    """Add derived, presentation-safe fields without leaking internals."""
    event = dict(row)
    for key in ("severity_components", "confidence_components", "confidence_explanation"):
        if isinstance(event.get(key), str):
            try:
                event[key] = json.loads(event[key])
            except (ValueError, TypeError):
                event[key] = None
    event["severity"] = event.get("severity")
    event["severity_label"] = event.get("severity_label")
    event["confidence_label"] = (
        (event.get("confidence_components") or {}).get("label")
        if isinstance(event.get("confidence_components"), dict)
        else None
    )
    event["is_structured_observation"] = bool(event.get("is_structured_observation"))
    event["credibility"] = {
        "score": event.get("credibility_score"),
        "label": "Source credibility",
        "explanation": "A provenance and independent-corroboration indicator; it ranks source metadata and does not judge whether a report is true.",
    }
    event["corroboration"] = {
        "level": event.get("corroboration_level"),
        "independent_publishers": event.get("independent_source_count"),
        "syndicated_publishers": event.get("syndicated_source_count"),
    }
    event["location"] = {
        "country": event.get("country"),
        "country_code": event.get("country_code"),
        "latitude": event.get("latitude"),
        "longitude": event.get("longitude"),
        "precision": event.get("location_precision") or "unknown",
        "text": event.get("location_text"),
    }
    return event


@router.get("/events")
def events(
    category: str | None = None,
    subcategory: str | None = None,
    country_code: str | None = None,
    min_importance: int = Query(1, ge=1, le=10),
    min_severity: float | None = Query(None, ge=0, le=10),
    min_confidence: float | None = Query(None, ge=0, le=1),
    event_state: str | None = None,
    provider: str | None = None,
    search: str | None = Query(None, max_length=200),
    start: str | None = None,
    end: str | None = None,
    sort: Literal["recent", "severity", "priority", "confidence"] = "recent",
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    user=Depends(get_optional_user),
):
    """Filtered event search with cursor pagination."""
    conditions = ["e.importance >= ?"]
    params: list = [min_importance]

    if category:
        conditions.append("e.category = ?")
        params.append(category)
    if subcategory:
        conditions.append("e.subcategory = ?")
        params.append(subcategory)
    if country_code:
        conditions.append("e.country_code = ?")
        params.append(country_code.upper())
    if min_severity is not None:
        conditions.append("e.severity >= ?")
        params.append(min_severity)
    if min_confidence is not None:
        conditions.append("e.confidence >= ?")
        params.append(min_confidence)
    if event_state:
        conditions.append("e.event_state = ?")
        params.append(event_state)
    if provider:
        conditions.append("e.provider_keys LIKE ?")
        params.append(f"%{provider}%")
    if search:
        conditions.append("(e.title LIKE ? OR e.summary LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if start:
        conditions.append("julianday(COALESCE(e.occurred_at, e.event_time)) >= julianday(?)")
        params.append(start)
    if end:
        conditions.append("julianday(COALESCE(e.occurred_at, e.event_time)) <= julianday(?)")
        params.append(end)

    order = {
        "recent": "COALESCE(e.occurred_at, e.event_time) DESC, e.id DESC",
        "severity": "COALESCE(e.severity, 0) DESC, e.id DESC",
        "priority": "COALESCE(e.priority_score, 0) DESC, e.id DESC",
        "confidence": "COALESCE(e.confidence, 0) DESC, e.id DESC",
    }[sort]

    decoded = _decode_cursor(cursor)
    if decoded:
        cursor_time, cursor_id = decoded
        # Keyset pagination for every sort mode. Comparing only on the sort key
        # re-served rows whenever several events shared the same severity or
        # timestamp, so the id is always the tie-breaker.
        if sort == "recent":
            conditions.append(
                "(COALESCE(e.occurred_at, e.event_time) < ? "
                "OR (COALESCE(e.occurred_at, e.event_time) = ? AND e.id < ?))"
            )
            params.extend([cursor_time, cursor_time, cursor_id])
        else:
            column = {
                "severity": "COALESCE(e.severity, 0)",
                "priority": "COALESCE(e.priority_score, 0)",
                "confidence": "COALESCE(e.confidence, 0)",
            }[sort]
            # ``cursor_time`` carries the numeric sort value for these modes.
            conditions.append(
                f"({column} < ? OR ({column} = ? AND e.id < ?))"
            )
            params.extend([cursor_time, cursor_time, cursor_id])

    conn = get_connection()
    try:
        rows = select_events(
            conn,
            where_clause=" AND ".join(conditions),
            params=params,
            order_clause=order,
            limit=limit + 1,
            user_id=user["id"] if user else None,
        )
    finally:
        conn.close()

    has_more = len(rows) > limit
    items = [_serialize_event(row) for row in rows[:limit]]
    return {
        "items": items,
        "next_cursor": _encode_cursor(items[-1], sort) if has_more and items else None,
        "has_more": has_more,
        "count": len(items),
        "filters": {
            "category": category, "subcategory": subcategory,
            "country_code": country_code, "min_importance": min_importance,
            "min_severity": min_severity, "min_confidence": min_confidence,
            "event_state": event_state, "search": search, "sort": sort,
        },
    }


@router.get("/events/latest")
def latest_events(
    limit: int = Query(300, ge=1, le=500),
    user=Depends(get_optional_user),
):
    conn = get_connection()
    try:
        rows = select_events(
            conn,
            order_clause="COALESCE(e.occurred_at, e.event_time) DESC, e.id DESC",
            limit=limit,
            user_id=user["id"] if user else None,
        )
    finally:
        conn.close()
    return [_serialize_event(row) for row in rows]


@router.get("/events/history")
def event_history(
    limit: int = Query(1000, ge=1, le=1000),
    user=Depends(get_optional_user),
):
    """Retained for backwards compatibility with the existing frontend."""
    conn = get_connection()
    try:
        rows = select_events(
            conn,
            order_clause="COALESCE(e.occurred_at, e.event_time) DESC, e.id DESC",
            limit=limit,
            user_id=user["id"] if user else None,
        )
    finally:
        conn.close()
    return [_serialize_event(row) for row in rows]


@router.get("/events/{event_id}")
async def event(event_id: int, user=Depends(get_optional_user)):
    conn = get_connection()
    try:
        result = select_event(conn, event_id, user_id=user["id"] if user else None)
        if not result:
            raise HTTPException(status_code=404, detail="Event not found")

        result = _serialize_event(result)

        result["sources"] = [
            dict(source)
            for source in conn.execute(
                """
                SELECT a.title, a.url, a.canonical_url, a.source, a.publisher,
                       a.publisher_domain, a.provider, a.published_at, a.first_seen_at,
                       a.last_seen_at, a.image_url, a.language, a.reporting_type,
                       a.is_independent, a.extraction_status, a.source_tier,
                       a.propaganda_risk, a.state_affiliated, a.source_region
                FROM articles a
                JOIN event_articles ea ON ea.article_id = a.id
                WHERE ea.event_id = ?
                ORDER BY COALESCE(a.published_at, a.first_seen_at) ASC
                """,
                (event_id,),
            ).fetchall()
        ]

        result["timeline"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT occurred_at, change_type, description, article_id, confidence
                FROM event_timeline WHERE event_id = ?
                ORDER BY occurred_at ASC
                """,
                (event_id,),
            ).fetchall()
        ]

        result["relationships"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT r.relationship, r.confidence, r.reason, r.evidence,
                       e.id AS event_id, e.title, e.category, e.country_code,
                       e.severity, COALESCE(e.occurred_at, e.event_time) AS occurred_at
                FROM event_relationships r
                JOIN events e ON e.id = r.target_event_id
                WHERE r.source_event_id = ?
                ORDER BY r.confidence DESC
                LIMIT 20
                """,
                (event_id,),
            ).fetchall()
        ]
        for relationship in result["relationships"]:
            if isinstance(relationship.get("evidence"), str):
                try:
                    relationship["evidence"] = json.loads(relationship["evidence"])
                except (ValueError, TypeError):
                    pass

        result["entities"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT en.id, en.name, en.entity_type, en.country_code, m.role, m.confidence
                FROM event_entity_mentions m
                JOIN entities en ON en.id = m.entity_id
                WHERE m.event_id = ?
                ORDER BY m.confidence DESC
                """,
                (event_id,),
            ).fetchall()
        ]

        # Image discovery is best effort and never blocks the response on errors.
        missing = [s for s in result["sources"][:5] if not s.get("image_url")]
        if missing:
            discovered = await asyncio.gather(
                *(discover_image_url(source["url"]) for source in missing),
                return_exceptions=True,
            )
            updates = []
            for source, image in zip(missing, discovered):
                if isinstance(image, str) and image:
                    source["image_url"] = image
                    updates.append((image, source["url"]))
            if updates:
                with write_connection() as write_conn:
                    for image, url in updates:
                        write_conn.execute(
                            "UPDATE articles SET image_url = ? WHERE url = ?", (image, url)
                        )

        return result
    finally:
        conn.close()


@router.get("/events/{event_id}/timeline")
def event_timeline(event_id: int):
    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Event not found")
        rows = conn.execute(
            """
            SELECT occurred_at, change_type, description, article_id, confidence
            FROM event_timeline WHERE event_id = ? ORDER BY occurred_at ASC
            """,
            (event_id,),
        ).fetchall()
        return {"event_id": event_id, "items": [dict(row) for row in rows]}
    finally:
        conn.close()


@router.get("/events/{event_id}/image")
async def event_image(event_id: int):
    conn = get_connection()
    try:
        sources = conn.execute(
            """
            SELECT a.url, a.image_url
            FROM event_articles ea
            JOIN articles a ON a.id = ea.article_id
            WHERE ea.event_id = ?
            ORDER BY a.id
            LIMIT 5
            """,
            (event_id,),
        ).fetchall()
        if not sources:
            raise HTTPException(status_code=404, detail="Event image not found")

        for source in sources:
            if source["image_url"] and source["image_url"].strip():
                return {"image_url": source["image_url"]}

        discovered = await asyncio.gather(
            *(discover_image_url(source["url"]) for source in sources),
            return_exceptions=True,
        )
        for source, image in zip(sources, discovered):
            if isinstance(image, str) and image:
                with write_connection() as write_conn:
                    write_conn.execute(
                        "UPDATE articles SET image_url = ? WHERE url = ?", (image, source["url"])
                    )
                return {"image_url": image}

        raise HTTPException(status_code=404, detail="Event image not found")
    finally:
        conn.close()


class SeedRequest(BaseModel):
    confirm: bool = Field(
        default=False,
        description="Must be true; demo data is clearly labelled and never production data.",
    )


@router.post("/events/seed")
def seed(payload: SeedRequest | None = None):
    """Insert clearly-labelled demonstration events.

    Only available when ``DEMO_DATA_ENABLED=true`` in a non-production
    environment. This route previously wrote fabricated events with no gate at
    all, which is exactly the kind of public endpoint that can corrupt data.
    """
    if not settings.demo_data_enabled or settings.is_production:
        raise HTTPException(
            status_code=403,
            detail=(
                "Demo data is disabled. Set DEMO_DATA_ENABLED=true in a "
                "development environment to enable sample events."
            ),
        )
    if payload is None or not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Send {\"confirm\": true} to confirm you want demonstration data inserted.",
        )

    demo = [
        ("[DEMO] Major earthquake strikes Japan", "natural_disaster", "earthquake", "Japan", "JP", 36.2048, 138.2529),
        ("[DEMO] Global economic policy update", "economic_financial", "economic_policy", "United States", "US", 37.0902, -95.7129),
        ("[DEMO] Technology and AI development announced", "cyber_technology", "technology_development", "United Kingdom", "GB", 55.3781, -3.4360),
        ("[DEMO] Flood warnings issued", "natural_disaster", "flood", "Sri Lanka", "LK", 7.8731, 80.7718),
    ]

    now = datetime.now(timezone.utc).isoformat()
    with write_connection() as conn:
        for title, category, subcategory, country, code, lat, lon in demo:
            conn.execute(
                """
                INSERT INTO events (
                    title, summary, category, subcategory, country, country_code,
                    latitude, longitude, location_precision, importance, confidence,
                    severity, severity_label, event_time, occurred_at, occurred_at_precision,
                    event_state, first_seen_at, last_seen_at, created_at, updated_at,
                    provider_keys, ai_assessment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'city', 5, 0.3, 5.0, 'moderate', ?, ?, 'timestamp',
                          'newly_detected', ?, ?, ?, ?, 'demo', ?)
                """,
                (
                    title,
                    "Demonstration record inserted by the seed endpoint. Not a real event.",
                    category, subcategory, country, code, lat, lon,
                    now, now, now, now, now, now,
                    "Demo record. This is sample data, not an intelligence assessment.",
                ),
            )
        return {"seeded": len(demo), "demo": True}
