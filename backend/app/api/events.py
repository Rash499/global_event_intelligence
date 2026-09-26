import asyncio
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database.db import get_connection
from ..database.queries import select_event, select_events
from .auth import get_optional_user


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
    user=Depends(get_optional_user),
):
    conn = get_connection()

    try:
        conditions = ["e.importance >= ?"]
        params = [min_importance]

        if category:
            conditions.append("e.category = ?")
            params.append(category)

        if country_code:
            conditions.append("e.country_code = ?")
            params.append(country_code)

        return select_events(
            conn,
            where_clause=" AND ".join(conditions),
            params=params,
            order_clause="e.event_time DESC",
            limit=limit,
            user_id=user["id"] if user else None,
        )

    finally:
        conn.close()


@router.get("/events/latest")
def latest_events(
    limit: int = Query(300, ge=1, le=500),
    user=Depends(get_optional_user),
):
    conn = get_connection()

    try:
        return select_events(
            conn,
            order_clause="e.event_time DESC",
            limit=limit,
            user_id=user["id"] if user else None,
        )

    finally:
        conn.close()


@router.get("/events/history")
def event_history(
    limit: int = Query(1000, ge=1, le=1000),
    user=Depends(get_optional_user),
):
    conn = get_connection()

    try:
        return select_events(
            conn,
            order_clause="e.event_time DESC, e.id DESC",
            limit=limit,
            user_id=user["id"] if user else None,
        )

    finally:
        conn.close()


@router.get("/events/{event_id}")
async def event(
    event_id: int,
    user=Depends(get_optional_user),
):
    conn = get_connection()

    try:
        result = select_event(
            conn,
            event_id,
            user_id=user["id"] if user else None,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Event not found")

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

        discovered_images = await asyncio.gather(
            *(discover_image_url(source["url"]) for source in sources)
        )
        image_url = next((url for url in discovered_images if url), None)

        if not image_url:
            raise HTTPException(status_code=404, detail="Event image not found")

        source_url = sources[discovered_images.index(image_url)]["url"]
        conn.execute(
            "UPDATE articles SET image_url = ? WHERE url = ?",
            (image_url, source_url),
        )
        conn.commit()
        return {"image_url": image_url}
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
