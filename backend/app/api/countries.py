from fastapi import APIRouter, Depends, Query

from .auth import get_optional_user
from ..database.db import get_connection
from ..database.queries import select_events


router = APIRouter(prefix="/api")


@router.get("/countries/{country_code}")
def country(
    country_code: str,
    limit: int = Query(200, ge=1, le=500),
    user=Depends(get_optional_user),
):
    conn = get_connection()

    try:
        code = country_code.upper()
        events = select_events(
            conn,
            where_clause="e.country_code = ?",
            params=(code,),
            order_clause="e.event_time DESC",
            limit=limit,
            user_id=user["id"] if user else None,
        )

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
    user=Depends(get_optional_user),
):
    conn = get_connection()

    try:
        code = country_code.upper()
        events = select_events(
            conn,
            where_clause="e.country_code = ?",
            params=(code,),
            order_clause="e.event_time DESC",
            limit=limit,
            user_id=user["id"] if user else None,
        )

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
