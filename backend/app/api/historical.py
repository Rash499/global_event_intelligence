from datetime import timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database.db import get_connection
from ..intelligence.historical import compare_periods, event_history, historical_stats
from ..rag.timestamps import parse_timestamp

router = APIRouter(prefix="/api/intelligence", tags=["historical-intelligence"])


def _date(value: str, field: str):
    parsed = parse_timestamp(value)
    if not parsed:
        raise HTTPException(status_code=422, detail=f"Invalid {field} timestamp")
    return parsed.astimezone(timezone.utc).isoformat()


@router.get("/history")
def history(start: str, end: str, country: str | None = None,
            category: str | None = None, limit: int = Query(50, ge=1, le=200)):
    start_iso, end_iso = _date(start, "start"), _date(end, "end")
    if parse_timestamp(start_iso) >= parse_timestamp(end_iso):
        raise HTTPException(status_code=422, detail="start must be earlier than end")
    conn = get_connection()
    try:
        stats = historical_stats(conn, start_iso, end_iso, country=country, category=category)
        rows = conn.execute(
            """SELECT e.id, e.title, e.summary, e.category, e.country, e.country_code,
                      e.importance, e.confidence, e.event_time
               FROM events e
               WHERE julianday(COALESCE(e.event_time,e.created_at)) >= julianday(?)
                 AND julianday(COALESCE(e.event_time,e.created_at)) < julianday(?)
                 AND (? IS NULL OR e.country_code = ?)
                 AND (? IS NULL OR e.category = ?)
               ORDER BY e.importance DESC, e.event_time DESC LIMIT ?""",
            (start_iso, end_iso, country, country, category, category, limit),
        ).fetchall()
        return {"start": start_iso, "end": end_iso, "statistics": stats,
                "events": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/trends")
def trends(start: str, end: str, country: str | None = None, category: str | None = None):
    start_iso, end_iso = _date(start, "start"), _date(end, "end")
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT substr(COALESCE(e.event_time,e.created_at),1,10) day,
                      COUNT(*) events, COALESCE(SUM(e.article_count),0) articles,
                      ROUND(AVG(e.importance),2) average_importance
               FROM events e
               WHERE julianday(COALESCE(e.event_time,e.created_at)) >= julianday(?)
                 AND julianday(COALESCE(e.event_time,e.created_at)) < julianday(?)
                 AND (? IS NULL OR e.country_code = ?)
                 AND (? IS NULL OR e.category = ?)
               GROUP BY day ORDER BY day""",
            (start_iso, end_iso, country, country, category, category),
        ).fetchall()
        return {"start": start_iso, "end": end_iso, "trend": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/categories/history")
def category_history(start: str, end: str):
    start_iso, end_iso = _date(start, "start"), _date(end, "end")
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT category, substr(COALESCE(event_time,created_at),1,10) day, COUNT(*) count
               FROM events
               WHERE julianday(COALESCE(event_time,created_at)) >= julianday(?)
                 AND julianday(COALESCE(event_time,created_at)) < julianday(?)
               GROUP BY category, day ORDER BY day, count DESC""",
            (start_iso, end_iso),
        ).fetchall()
        return {"trend": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/countries/history")
def countries_history(start: str, end: str, limit: int = Query(20, ge=1, le=100)):
    start_iso, end_iso = _date(start, "start"), _date(end, "end")
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT country_code, country, COUNT(*) events, COALESCE(SUM(article_count),0) articles,
                      COUNT(DISTINCT category) categories
               FROM events
               WHERE julianday(COALESCE(event_time,created_at)) >= julianday(?)
                 AND julianday(COALESCE(event_time,created_at)) < julianday(?)
               GROUP BY country_code, country ORDER BY events DESC LIMIT ?""",
            (start_iso, end_iso, limit),
        ).fetchall()
        return {"countries": [dict(r) for r in rows]}
    finally:
        conn.close()


class Period(BaseModel):
    start: str
    end: str


class CompareRequest(BaseModel):
    period_a: Period
    period_b: Period
    scope: dict = Field(default_factory=dict)


@router.post("/compare")
def compare(request: CompareRequest):
    a = {"start": _date(request.period_a.start, "period_a.start"),
         "end": _date(request.period_a.end, "period_a.end")}
    b = {"start": _date(request.period_b.start, "period_b.start"),
         "end": _date(request.period_b.end, "period_b.end")}
    if parse_timestamp(a["start"]) >= parse_timestamp(a["end"]) or parse_timestamp(b["start"]) >= parse_timestamp(b["end"]):
        raise HTTPException(status_code=422, detail="Each period start must be earlier than its end")
    conn = get_connection()
    try:
        return compare_periods(conn, a, b, request.scope)
    finally:
        conn.close()


@router.get("/events/{event_id}/timeline")
def event_timeline(event_id: int):
    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Event not found")
        return event_history(conn, event_id)
    finally:
        conn.close()


@router.get("/events/{event_id}/related")
def related_events(event_id: int):
    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Event not found")
        return {"event_id": event_id, "related_events": event_history(conn, event_id)["related_events"]}
    finally:
        conn.close()


@router.get("/events/{event_id}/sources")
def event_sources(event_id: int):
    conn = get_connection()
    try:
        if not conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Event not found")
        history = event_history(conn, event_id)
        return {"event_id": event_id, "source_diversity": history["source_diversity"],
                "sources": history["timeline"]}
    finally:
        conn.close()
