from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Query

from ..database.db import get_connection


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

        return urljoin(str(response.url), parser.image_url)

    except (httpx.HTTPError, ValueError):
        return None


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

        return [
            dict(row)
            for row in conn.execute(sql, params).fetchall()
        ]

    finally:
        conn.close()


@router.get("/events/latest")
def latest_events(limit: int = Query(300, ge=1, le=500)):
    conn = get_connection()

    try:
        return [
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

    finally:
        conn.close()


@router.get("/events/history")
def event_history(limit: int = Query(1000, ge=1, le=1000)):
    conn = get_connection()

    try:
        return [
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
            return {"error": "Event not found"}

        result = dict(row)
        result["sources"] = [
            dict(source)
            for source in conn.execute(
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

            image_url = await discover_image_url(source["url"])
            if not image_url:
                continue

            source["image_url"] = image_url
            conn.execute(
                "UPDATE articles SET image_url = ? WHERE url = ?",
                (image_url, source["url"]),
            )

        conn.commit()
        return result

    finally:
        conn.close()


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
        return {"seeded": len(demo)}

    finally:
        conn.close()
