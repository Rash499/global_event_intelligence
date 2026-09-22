from fastapi import APIRouter

from ..database.db import get_connection


router = APIRouter(prefix="/api")


@router.get("/statistics/global")
def statistics():
    conn = get_connection()

    try:
        total = conn.execute(
            "SELECT COUNT(*) c FROM events"
        ).fetchone()["c"]
        major = conn.execute(
            "SELECT COUNT(*) c FROM events WHERE importance >= 8"
        ).fetchone()["c"]
        countries = conn.execute(
            """
            SELECT COUNT(DISTINCT country_code) c
            FROM events
            WHERE country_code IS NOT NULL
            """
        ).fetchone()["c"]
        categories = [
            dict(row)
            for row in conn.execute(
                """
                SELECT category, COUNT(*) AS count
                FROM events
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
                """
            ).fetchall()
        ]
        countries_by_event_count = [
            dict(row)
            for row in conn.execute(
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
