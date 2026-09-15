from fastapi import APIRouter, Query
from ..database.db import get_connection
from ..ingestion.service import ingest

router = APIRouter(prefix="/api")

@router.get("/health")
def health():
    return {"status": "ok", "service": "global-event-intelligence-api"}

@router.get("/events")
def events(category: str | None = None, country_code: str | None = None,
           min_importance: int = Query(1, ge=1, le=10), limit: int = Query(50, ge=1, le=200)):
    conn = get_connection()
    sql = "SELECT * FROM events WHERE importance >= ?"
    params = [min_importance]
    if category:
        sql += " AND category = ?"
        params.append(category)
    if country_code:
        sql += " AND country_code = ?"
        params.append(country_code)
    sql += " ORDER BY event_time DESC LIMIT ?"
    params.append(limit)
    rows = [dict(x) for x in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows

@router.get("/events/latest")
def latest_events(limit: int = Query(50, ge=1, le=200)):
    conn = get_connection()
    rows = [dict(x) for x in conn.execute(
        "SELECT * FROM events ORDER BY event_time DESC LIMIT ?", (limit,)
    ).fetchall()]
    conn.close()
    return rows

@router.get("/events/{event_id}")
def event(event_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Event not found"}
    result = dict(row)
    result["sources"] = [
        dict(x) for x in conn.execute(
            """SELECT a.title,a.url,a.source,a.published_at
               FROM articles a JOIN event_articles ea ON ea.article_id=a.id
               WHERE ea.event_id=?""", (event_id,)
        ).fetchall()
    ]
    conn.close()
    return result

@router.get("/countries/{country_code}")
def country(country_code: str):
    conn = get_connection()
    events = [dict(x) for x in conn.execute(
        "SELECT * FROM events WHERE country_code=? ORDER BY event_time DESC LIMIT 100",
        (country_code.upper(),)
    ).fetchall()]
    conn.close()
    return {"country_code": country_code.upper(), "events": events, "event_count": len(events)}

@router.get("/statistics/global")
def statistics():
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    major = conn.execute("SELECT COUNT(*) c FROM events WHERE importance >= 8").fetchone()["c"]
    countries = conn.execute(
        "SELECT COUNT(DISTINCT country_code) c FROM events WHERE country_code IS NOT NULL"
    ).fetchone()["c"]
    categories = [
        dict(x) for x in conn.execute(
            "SELECT category, COUNT(*) count FROM events GROUP BY category ORDER BY count DESC"
        ).fetchall()
    ]
    conn.close()
    return {"total_events": total, "major_events": major, "countries_with_events": countries, "categories": categories}

@router.post("/ingestion/run")
async def run_ingestion():
    return await ingest()

@router.post("/events/seed")
def seed():
    conn = get_connection()
    demo = [
        ("Major earthquake strikes Japan", "A demonstration high-importance natural disaster event.", "natural_disaster", "Japan", "JP", 36.2048, 138.2529, 9, .94),
        ("Global economic policy update", "A demonstration economic event for the dashboard.", "economy", "United States", "US", 37.0902, -95.7129, 7, .91),
        ("Technology and AI development announced", "A demonstration technology event.", "technology", "United Kingdom", "GB", 55.3781, -3.4360, 6, .86),
        ("Flood warnings issued", "A demonstration environment and disaster event.", "environment", "Sri Lanka", "LK", 7.8731, 80.7718, 7, .90),
    ]
    for row in demo:
        conn.execute(
            """INSERT INTO events(title,summary,category,country,country_code,latitude,longitude,
               importance,confidence,event_time) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'))""", row
        )
    conn.commit()
    conn.close()
    return {"seeded": len(demo)}
