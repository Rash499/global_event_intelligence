from fastapi import APIRouter, Query

from ..database.db import get_connection


router = APIRouter(prefix="/api")


@router.get("/countries/{country_code}")
def country(
    country_code: str,
    limit: int = Query(200, ge=1, le=500),
):
    conn = get_connection()

    try:
        code = country_code.upper()
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM events
                WHERE country_code = ?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (code, limit),
            ).fetchall()
        ]

        return {
            "country_code": code,
            "events": events,
            "event_count": len(events),
        }

    finally:
        conn.close()


@router.get("/countries/{country_code}/intelligence")
def country_intelligence(
    country_code: str,
    limit: int = Query(500, ge=1, le=500),
):
    conn = get_connection()

    try:
        code = country_code.upper()
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM events
                WHERE country_code = ?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (code, limit),
            ).fetchall()
        ]

        categories = {}
        for event in events:
            category = event.get("category") or "unknown"
            categories[category] = categories.get(category, 0) + 1

        return {
            "country_code": code,
            "total_events": len(events),
            "major_events": sum(
                1 for event in events if (event.get("importance") or 0) >= 8
            ),
            "category_breakdown": [
                {"category": category, "count": count}
                for category, count in sorted(
                    categories.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "events": events,
        }

    finally:
        conn.close()
