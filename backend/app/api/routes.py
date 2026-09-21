from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Query

from ..database.db import get_connection
from ..ingestion.service import ingest


router = APIRouter(prefix="/api")


class ImageMetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image_url = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta" or self.image_url:
            return

        values = {name.lower(): value for name, value in attrs}

        image_name = values.get(
            "property",
            values.get("name", "")
        ).lower()

        if image_name in {"og:image", "twitter:image"}:
            self.image_url = values.get("content")


async def discover_image_url(url: str) -> str | None:
    parsed_url = urlparse(url)

    if parsed_url.scheme not in {"http", "https"}:
        return None

    try:
        async with httpx.AsyncClient(
            timeout=8,
            follow_redirects=True,
            headers={
                "User-Agent": "GlobalEventIntelligence/1.0"
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        parser = ImageMetaParser()
        parser.feed(response.text[:1_000_000])

        if not parser.image_url:
            return None

        image_url = parser.image_url

        return urljoin(
            str(response.url),
            image_url
        )

    except (httpx.HTTPError, ValueError):
        return None


# =========================================================
# HEALTH
# =========================================================

@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "global-event-intelligence-api"
    }


# =========================================================
# EVENTS
# =========================================================

@router.get("/events")
def events(
    category: str | None = None,
    country_code: str | None = None,
    min_importance: int = Query(1, ge=1, le=10),
    limit: int = Query(50, ge=1, le=200),
):
    conn = get_connection()

    try:
        sql = """
            SELECT *
            FROM events
            WHERE importance >= ?
        """

        params = [min_importance]

        if category:
            sql += " AND category = ?"
            params.append(category)

        if country_code:
            sql += " AND country_code = ?"
            params.append(country_code)

        sql += """
            ORDER BY event_time DESC
            LIMIT ?
        """

        params.append(limit)

        rows = [
            dict(row)
            for row in conn.execute(
                sql,
                params
            ).fetchall()
        ]

        return rows

    finally:
        conn.close()


@router.get("/events/latest")
def latest_events(
    limit: int = Query(300, ge=1, le=500)
):
    conn = get_connection()

    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM events
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]

        return rows

    finally:
        conn.close()


@router.get("/events/history")
def event_history(
    limit: int = Query(1000, ge=1, le=1000)
):
    conn = get_connection()

    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM events
                ORDER BY event_time DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]

        return rows

    finally:
        conn.close()


@router.get("/events/{event_id}")
async def event(event_id: int):
    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM events WHERE id=?",
            (event_id,),
        ).fetchone()

        if not row:
            return {
                "error": "Event not found"
            }

        result = dict(row)

        result["sources"] = [
            dict(x)
            for x in conn.execute(
                """
                SELECT
                    a.title,
                    a.url,
                    a.source,
                    a.published_at,
                    a.image_url
                FROM articles a
                JOIN event_articles ea
                    ON ea.article_id = a.id
                WHERE ea.event_id = ?
                """,
                (event_id,),
            ).fetchall()
        ]

        for source in result["sources"][:5]:
            if source.get("image_url"):
                continue

            image_url = await discover_image_url(
                source["url"]
            )

            if not image_url:
                continue

            source["image_url"] = image_url

            conn.execute(
                """
                UPDATE articles
                SET image_url = ?
                WHERE url = ?
                """,
                (
                    image_url,
                    source["url"],
                ),
            )

        conn.commit()

        return result

    finally:
        conn.close()


# =========================================================
# COUNTRIES
# =========================================================

@router.get("/countries/{country_code}")
def country(
    country_code: str,
    limit: int = Query(200, ge=1, le=500),
):
    conn = get_connection()

    try:
        code = country_code.upper()

        events = [
            dict(x)
            for x in conn.execute(
                """
                SELECT *
                FROM events
                WHERE country_code = ?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (
                    code,
                    limit,
                ),
            ).fetchall()
        ]

        return {
            "country_code": code,
            "events": events,
            "event_count": len(events),
        }

    finally:
        conn.close()


# =========================================================
# GLOBAL STATISTICS
# =========================================================

@router.get("/statistics/global")
def statistics():
    conn = get_connection()

    try:
        total = conn.execute(
            """
            SELECT COUNT(*) c
            FROM events
            """
        ).fetchone()["c"]

        major = conn.execute(
            """
            SELECT COUNT(*) c
            FROM events
            WHERE importance >= 8
            """
        ).fetchone()["c"]

        countries = conn.execute(
            """
            SELECT COUNT(DISTINCT country_code) c
            FROM events
            WHERE country_code IS NOT NULL
            """
        ).fetchone()["c"]

        categories = [
            dict(x)
            for x in conn.execute(
                """
                SELECT
                    category,
                    COUNT(*) AS count
                FROM events
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
                """
            ).fetchall()
        ]

        countries_by_event_count = [
            dict(x)
            for x in conn.execute(
                """
                SELECT
                    country,
                    country_code,
                    COUNT(*) AS event_count,
                    MAX(importance) AS max_importance
                FROM events
                WHERE country_code IS NOT NULL
                GROUP BY country_code
                ORDER BY event_count DESC
                LIMIT 50
                """
            ).fetchall()
        ]

        return {
            "total_events": total,
            "major_events": major,
            "countries_with_events": countries,
            "categories": categories,
            "countries_by_event_count": countries_by_event_count,
        }

    finally:
        conn.close()


# =========================================================
# INGESTION
# =========================================================

@router.post("/ingestion/run")
async def run_ingestion():
    return await ingest()


# =========================================================
# DEMO / SEED DATA
# =========================================================

@router.post("/events/seed")
def seed():
    conn = get_connection()

    try:
        demo = [
            (
                "Major earthquake strikes Japan",
                "A demonstration high-importance natural disaster event.",
                "natural_disaster",
                "Japan",
                "JP",
                36.2048,
                138.2529,
                9,
                0.94,
            ),
            (
                "Global economic policy update",
                "A demonstration economic event for the dashboard.",
                "economy",
                "United States",
                "US",
                37.0902,
                -95.7129,
                7,
                0.91,
            ),
            (
                "Technology and AI development announced",
                "A demonstration technology event.",
                "technology",
                "United Kingdom",
                "GB",
                55.3781,
                -3.4360,
                6,
                0.86,
            ),
            (
                "Flood warnings issued",
                "A demonstration environment and disaster event.",
                "environment",
                "Sri Lanka",
                "LK",
                7.8731,
                80.7718,
                7,
                0.90,
            ),
        ]

        for row in demo:
            conn.execute(
                """
                INSERT INTO events(
                    title,
                    summary,
                    category,
                    country,
                    country_code,
                    latitude,
                    longitude,
                    importance,
                    confidence,
                    event_time
                )
                VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')
                )
                """,
                row,
            )

        conn.commit()

        return {
            "seeded": len(demo)
        }

    finally:
        conn.close()


# =========================================================
# COUNTRY INTELLIGENCE
# =========================================================

@router.get("/countries/{country_code}/intelligence")
def country_intelligence(
    country_code: str,
    limit: int = Query(500, ge=1, le=500),
):
    conn = get_connection()

    try:
        code = country_code.upper()

        events = [
            dict(x)
            for x in conn.execute(
                """
                SELECT *
                FROM events
                WHERE country_code = ?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (
                    code,
                    limit,
                ),
            ).fetchall()
        ]

        total_events = len(events)

        major_events = sum(
            1
            for event in events
            if (event.get("importance") or 0) >= 8
        )

        categories = {}

        for event in events:
            category = event.get("category") or "unknown"

            categories[category] = (
                categories.get(category, 0) + 1
            )

        category_breakdown = [
            {
                "category": category,
                "count": count,
            }
            for category, count in sorted(
                categories.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]

        return {
            "country_code": code,
            "total_events": total_events,
            "major_events": major_events,
            "category_breakdown": category_breakdown,
            "events": events,
        }

    finally:
        conn.close()