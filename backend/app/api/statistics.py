from fastapi import APIRouter
from datetime import datetime, timedelta

from ..database.db import get_connection


router = APIRouter(prefix="/api")


def _safe_date(value):
    if not value:
        return None

    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        return value.date().isoformat()
    except (TypeError, ValueError):
        return None


def _build_statistics_payload(conn):
    total = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
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

    timeline_rows = conn.execute(
        """
        SELECT
            COALESCE(date(event_time), date(created_at)) AS day,
            COUNT(*) AS event_count,
            SUM(CASE WHEN importance >= 8 THEN 1 ELSE 0 END) AS major_count
        FROM events
        WHERE event_time IS NOT NULL OR created_at IS NOT NULL
        GROUP BY COALESCE(date(event_time), date(created_at))
        ORDER BY day DESC
        LIMIT 14
        """
    ).fetchall()

    timeline = [
        {
            "date": row["day"],
            "count": row["event_count"],
            "major_count": row["major_count"],
        }
        for row in reversed(timeline_rows)
    ]

    category_breakdown = [
        {
            "category": row["category"],
            "count": row["count"],
            "major_count": conn.execute(
                "SELECT COUNT(*) FROM events WHERE category = ? AND importance >= 8",
                (row["category"],),
            ).fetchone()[0],
            "average_importance": round(
                conn.execute(
                    "SELECT AVG(importance) FROM events WHERE category = ?",
                    (row["category"],),
                ).fetchone()[0] or 0,
                2,
            ),
        }
        for row in categories
    ]

    return {
        "total_events": total,
        "major_events": major,
        "countries_with_events": countries,
        "categories": categories,
        "countries_by_event_count": countries_by_event_count,
        "timeline": timeline,
        "category_breakdown": category_breakdown,
    }


@router.get("/statistics/global")
def statistics():
    conn = get_connection()

    try:
        return _build_statistics_payload(conn)

    finally:
        conn.close()


@router.get("/statistics/overview")
def statistics_overview():
    conn = get_connection()

    try:
        return _build_statistics_payload(conn)

    finally:
        conn.close()
