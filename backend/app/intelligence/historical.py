"""Historical intelligence services built on the existing events/articles model.

All numerical results come from SQLite. Change and conflict detection is
deterministic; Ollama is not required to calculate historical facts.
"""
import re
from collections import Counter
from datetime import timezone
from urllib.parse import urlparse

from .clustering import haversine_distance_km
from ..rag.timestamps import parse_timestamp, to_iso

CASUALTY_RE = re.compile(r"\b(?:killed|dead|deaths?|casualties|injured|wounded)\D{0,24}(\d{1,7})\b", re.I)
NUMBER_FIRST_RE = re.compile(r"\b(\d{1,7})\s+(?:people|persons|victims)\s+(?:were\s+)?(?:killed|dead|injured|wounded)\b", re.I)


def _article_text(row):
    return " ".join(str(row.get(k) or "") for k in ("title", "description"))


def _extract_claims(text):
    claims = []
    for match in list(CASUALTY_RE.finditer(text)) + list(NUMBER_FIRST_RE.finditer(text)):
        claims.append({"claim_type": "casualties", "value": int(match.group(1))})
    return claims


def _domain(url, source):
    try:
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") or (source or "unknown")
    except ValueError:
        return source or "unknown"


def event_articles(conn, event_id):
    rows = conn.execute(
        """
        SELECT a.id article_id, a.title, a.description, a.url, a.source,
               a.published_at, e.event_time, e.title event_title,
               e.summary event_summary, e.category, e.country, e.country_code,
               e.latitude, e.longitude, e.importance, e.confidence,
               e.corroboration_level
        FROM articles a
        JOIN event_articles ea ON ea.article_id = a.id
        JOIN events e ON e.id = ea.event_id
        WHERE ea.event_id = ?
        ORDER BY COALESCE(a.published_at, e.event_time, e.created_at), a.id
        """,
        (event_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def build_timeline(conn, event_id):
    rows = event_articles(conn, event_id)
    timeline = []
    for row in rows:
        timestamp = to_iso(row["published_at"]) or to_iso(row["event_time"])
        timeline.append({
            "timestamp": timestamp,
            "article_id": row["article_id"],
            "event_id": event_id,
            "source": row["source"] or _domain(row["url"], None),
            "domain": _domain(row["url"], row["source"]),
            "title": row["title"],
            "summary": row["description"] or row["event_summary"] or "",
            "event_status": "reported",
            "importance": row["importance"],
            "confidence": row["confidence"],
            "verification_status": row["corroboration_level"] or "insufficient_evidence",
            "location": {"country": row["country"], "country_code": row["country_code"],
                         "latitude": row["latitude"], "longitude": row["longitude"]},
            "category": row["category"],
            "changes": [],
            "evidence_reference": {"article_id": row["article_id"], "url": row["url"]},
        })
    return timeline


def source_diversity(conn, event_id):
    rows = event_articles(conn, event_id)
    domains = [_domain(r["url"], r["source"]) for r in rows if _domain(r["url"], r["source"])]
    timestamps = [parse_timestamp(r["published_at"]) or parse_timestamp(r["event_time"]) for r in rows]
    timestamps = [t for t in timestamps if t]
    first = min(timestamps).astimezone(timezone.utc).isoformat() if timestamps else None
    latest = max(timestamps).astimezone(timezone.utc).isoformat() if timestamps else None
    duration = (max(timestamps) - min(timestamps)).total_seconds() if len(timestamps) > 1 else 0
    return {
        "total_articles": len(rows),
        "unique_domains": len(set(domains)),
        "unique_sources": len(set((r["source"] or "").strip().lower() for r in rows if r["source"])),
        "independent_domain_count": len(set(domains)),
        "first_reported": first,
        "latest_reported": latest,
        "reporting_duration_seconds": int(duration),
        "domains": sorted(set(domains)),
    }


def detect_changes(conn, event_id):
    rows = event_articles(conn, event_id)
    changes = []
    previous = None
    for row in rows:
        text = _article_text(row)
        claims = _extract_claims(text)
        current = {"row": row, "claims": claims}
        if previous:
            prev_row = previous["row"]
            if claims and previous["claims"] and claims[0]["value"] != previous["claims"][0]["value"]:
                changes.append({"type": "casualty_change", "from": previous["claims"][0]["value"],
                                "to": claims[0]["value"], "article_id": row["article_id"]})
            if row["country_code"] and prev_row["country_code"] and row["country_code"] != prev_row["country_code"]:
                changes.append({"type": "location_change", "from": prev_row["country_code"],
                                "to": row["country_code"], "article_id": row["article_id"]})
        if re.search(r"\b(official|government|police|authorities)\b", text, re.I):
            changes.append({"type": "official_statement", "article_id": row["article_id"]})
        previous = current

    claims = []
    for row in rows:
        for claim in _extract_claims(_article_text(row)):
            claims.append({"article_id": row["article_id"], "source": row["source"],
                            "timestamp": to_iso(row["published_at"]) or to_iso(row["event_time"]),
                            **claim})
    values = sorted({c["value"] for c in claims})
    if len(values) > 1:
        changes.append({"type": "conflicting_information", "claim_type": "casualties",
                        "values": values, "claims": claims})
    return changes, claims


def ensure_relationships(conn, event_id):
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        return []
    rows = conn.execute(
        "SELECT * FROM events WHERE id != ? ORDER BY event_time DESC LIMIT 500", (event_id,)
    ).fetchall()
    relationships = []
    for other in rows:
        rel = None
        confidence = 0.0
        reason = None
        if event["latitude"] is not None and event["longitude"] is not None and other["latitude"] is not None and other["longitude"] is not None:
            distance = haversine_distance_km(event["latitude"], event["longitude"], other["latitude"], other["longitude"])
            if distance <= 100:
                rel, confidence, reason = "same_location", 0.88, f"Locations are approximately {distance:.1f} km apart."
        if not rel and event["category"] and event["category"] == other["category"] and event["country_code"] == other["country_code"]:
            rel, confidence, reason = "same_category", 0.78, "Both events share country and category."
        if not rel and event["country_code"] and event["country_code"] == other["country_code"]:
            rel, confidence, reason = "same_country", 0.65, "Both events are attributed to the same country."
        if rel:
            relationships.append({"event_id": other["id"], "relationship": rel,
                                  "confidence": confidence, "reason": reason,
                                  "title": other["title"], "category": other["category"],
                                  "country": other["country"], "event_time": to_iso(other["event_time"])})
    return relationships[:20]


def historical_stats(conn, start, end, country=None, region_codes=None, category=None):
    conditions = ["julianday(COALESCE(e.event_time, e.created_at)) >= julianday(?)",
                  "julianday(COALESCE(e.event_time, e.created_at)) < julianday(?)"]
    params = [start, end]
    if country:
        conditions.append("e.country_code = ?")
        params.append(country)
    if region_codes:
        conditions.append("e.country_code IN (%s)" % ",".join("?" * len(region_codes)))
        params.extend(region_codes)
    if category:
        conditions.append("e.category = ?")
        params.append(category)
    where = " AND ".join(conditions)
    summary = conn.execute(
        f"""SELECT COUNT(*) events, COALESCE(SUM(e.article_count),0) articles,
                   COALESCE(AVG(e.importance),0) average_importance,
                   COALESCE(AVG(e.confidence),0) average_confidence,
                   COUNT(DISTINCT e.country_code) countries,
                   COUNT(CASE WHEN e.importance >= 8 THEN 1 END) major_events
            FROM events e WHERE {where}""", params).fetchone()
    categories = conn.execute(
        f"SELECT e.category, COUNT(*) count FROM events e WHERE {where} GROUP BY e.category ORDER BY count DESC", params).fetchall()
    countries = conn.execute(
        f"SELECT e.country_code, e.country, COUNT(*) count FROM events e WHERE {where} GROUP BY e.country_code, e.country ORDER BY count DESC LIMIT 20", params).fetchall()
    return {"summary": dict(summary), "categories": [dict(x) for x in categories],
            "countries": [dict(x) for x in countries]}


def compare_periods(conn, period_a, period_b, scope=None):
    scope = scope or {}
    a = historical_stats(conn, period_a["start"], period_a["end"], scope.get("country"), scope.get("region_codes"), scope.get("category"))
    b = historical_stats(conn, period_b["start"], period_b["end"], scope.get("country"), scope.get("region_codes"), scope.get("category"))
    def delta(key):
        return (b["summary"].get(key) or 0) - (a["summary"].get(key) or 0)
    return {
        "period_a": a, "period_b": b,
        "summary": {"events_change": delta("events"), "articles_change": delta("articles"),
                    "major_events_change": delta("major_events"),
                    "average_importance_change": round(delta("average_importance"), 3),
                    "average_confidence_change": round(delta("average_confidence"), 3)},
        "category_changes": _merge_deltas(a["categories"], b["categories"], "category"),
        "country_changes": _merge_deltas(a["countries"], b["countries"], "country_code"),
    }


def _merge_deltas(a, b, key):
    left = {x[key]: x["count"] for x in a}
    right = {x[key]: x["count"] for x in b}
    return [{"key": k, "before": left.get(k, 0), "after": right.get(k, 0), "change": right.get(k, 0)-left.get(k, 0)}
            for k in sorted(set(left)|set(right), key=lambda x: -(right.get(x, 0)))]


def event_momentum(conn, event_id):
    rows = event_articles(conn, event_id)
    if len(rows) < 2:
        return {"state": "insufficient_data", "report_counts": [], "message": "At least two reports are required."}
    buckets = Counter()
    for row in rows:
        ts = parse_timestamp(row["published_at"]) or parse_timestamp(row["event_time"])
        if ts:
            buckets[ts.strftime("%Y-%m-%d %H:00")] += 1
    counts = list(buckets.values())
    if len(counts) < 2:
        state = "insufficient_data"
    elif counts[-1] > counts[0]:
        state = "increasing"
    elif counts[-1] < counts[0]:
        state = "declining"
    else:
        state = "stable"
    return {"state": state, "report_counts": [{"timestamp": k, "count": v} for k, v in sorted(buckets.items())],
            "message": f"Reporting activity is {state} during the observed period."}


def event_history(conn, event_id):
    timeline = build_timeline(conn, event_id)
    changes, claims = detect_changes(conn, event_id)
    diversity = source_diversity(conn, event_id)
    momentum = event_momentum(conn, event_id)
    relationships = ensure_relationships(conn, event_id)
    for item in timeline:
        item["changes"] = [c for c in changes if c.get("article_id") == item["article_id"]]
    return {"event_id": event_id, "timeline": timeline, "changes": changes,
            "claims": claims, "conflicting_reports": any(c["type"] == "conflicting_information" for c in changes),
            "source_diversity": diversity, "momentum": momentum,
            "related_events": relationships}CASUALTY_PATTERNS = [
    ("killed", re.compile(
        r"\b(\d{1,7})\s+(?:(?:people|persons|individuals|victims)\s+)?"
        r"(?:were\s+)?(?:reported\s+as\s+)?killed\b", re.I)),
    ("injured", re.compile(
        r"\b(\d{1,7})\s+(?:(?:people|persons|individuals|victims)\s+)?"
        r"(?:were\s+)?(?:reported\s+as\s+)?(?:injured|wounded)\b", re.I)),
    ("casualties", re.compile(r"\b(\d{1,7})\s+(?:total\s+)?casualties\b", re.I)),
    ("deaths", re.compile(
        r"\b(\d{1,7})\s+(?:(?:people|persons|individuals|victims)\s+)?"
        r"(?:were\s+)?(?:reported\s+)?(?:dead|deaths?|fatalities)\b", re.I)),
    ("killed", re.compile(r"\b(?:killed|dead|deaths?|fatalities)\s*[:,-]?\s*(\d{1,7})\b", re.I)),
    ("injured", re.compile(r"\b(?:injured|wounded|injuries)\s*[:,-]?\s*(\d{1,7})\b", re.I)),
    ("casualties", re.compile(r"\bcasualties\s*[:,-]?\s*(\d{1,7})\b", re.I)),
]


def _domain(url, source):
    try:
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") or (source or "unknown")
    except ValueError:
        return source or "unknown"


def event_articles(conn, event_id):
    rows = conn.execute(
        """
        SELECT a.id article_id, a.title, a.description, a.url, a.source,
               a.published_at, e.event_time, e.title event_title,
               e.summary event_summary, e.category, e.country, e.country_code,
               e.latitude, e.longitude, e.importance, e.confidence,
               e.corroboration_level
        FROM articles a
        JOIN event_articles ea ON ea.article_id = a.id
        JOIN events e ON e.id = ea.event_id
        WHERE ea.event_id = ?
        ORDER BY COALESCE(a.published_at, e.event_time, e.created_at), a.id
        """,
        (event_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def build_timeline(conn, event_id):
    rows = event_articles(conn, event_id)
    timeline = []
    for row in rows:
        timestamp = to_iso(row["published_at"]) or to_iso(row["event_time"])
        timeline.append({
            "timestamp": timestamp,
            "article_id": row["article_id"],
            "event_id": event_id,
            "source": row["source"] or _domain(row["url"], None),
            "domain": _domain(row["url"], row["source"]),
            "title": row["title"],
            "summary": row["description"] or row["event_summary"] or "",
            "event_status": "reported",
            "importance": row["importance"],
            "confidence": row["confidence"],
            "verification_status": row["corroboration_level"] or "insufficient_evidence",
            "location": {"country": row["country"], "country_code": row["country_code"],
                         "latitude": row["latitude"], "longitude": row["longitude"]},
            "category": row["category"],
            "changes": [],
            "evidence_reference": {"article_id": row["article_id"], "url": row["url"]},
        })
    return timeline


def source_diversity(conn, event_id):
    rows = event_articles(conn, event_id)
    domains = [_domain(r["url"], r["source"]) for r in rows if _domain(r["url"], r["source"])]
    timestamps = [parse_timestamp(r["published_at"]) or parse_timestamp(r["event_time"]) for r in rows]
    timestamps = [t for t in timestamps if t]
    first = min(timestamps).astimezone(timezone.utc).isoformat() if timestamps else None
    latest = max(timestamps).astimezone(timezone.utc).isoformat() if timestamps else None
    duration = (max(timestamps) - min(timestamps)).total_seconds() if len(timestamps) > 1 else 0
    return {
        "total_articles": len(rows),
        "unique_domains": len(set(domains)),
        "unique_sources": len(set((r["source"] or "").strip().lower() for r in rows if r["source"])),
        "independent_domain_count": len(set(domains)),
        "first_reported": first,
        "latest_reported": latest,
        "reporting_duration_seconds": int(duration),
        "domains": sorted(set(domains)),
    }


def detect_changes(conn, event_id):
    rows = event_articles(conn, event_id)
    changes = []
    previous = None
    for row in rows:
        text = _article_text(row)
        claims = _extract_claims(text)
        current = {"row": row, "claims": claims}
        if previous:
            prev_row = previous["row"]
            if claims and previous["claims"] and claims[0]["value"] != previous["claims"][0]["value"]:
                changes.append({"type": "casualty_change", "from": previous["claims"][0]["value"],
                                "to": claims[0]["value"], "article_id": row["article_id"]})
            if row["country_code"] and prev_row["country_code"] and row["country_code"] != prev_row["country_code"]:
                changes.append({"type": "location_change", "from": prev_row["country_code"],
                                "to": row["country_code"], "article_id": row["article_id"]})
        if re.search(r"\b(official|government|police|authorities)\b", text, re.I):
            changes.append({"type": "official_statement", "article_id": row["article_id"]})
        previous = current

    claims = []
    for row in rows:
        for claim in _extract_claims(_article_text(row)):
            claims.append({"article_id": row["article_id"], "source": row["source"],
                            "timestamp": to_iso(row["published_at"]) or to_iso(row["event_time"]),
                            **claim})
    values = sorted({c["value"] for c in claims})
    if len(values) > 1:
        changes.append({"type": "conflicting_information", "claim_type": "casualties",
                        "values": values, "claims": claims})
    return changes, claims


def ensure_relationships(conn, event_id):
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        return []
    rows = conn.execute(
        "SELECT * FROM events WHERE id != ? ORDER BY event_time DESC LIMIT 500", (event_id,)
    ).fetchall()
    relationships = []
    for other in rows:
        rel = None
        confidence = 0.0
        reason = None
        if event["latitude"] is not None and event["longitude"] is not None and other["latitude"] is not None and other["longitude"] is not None:
            distance = haversine_distance_km(event["latitude"], event["longitude"], other["latitude"], other["longitude"])
            if distance <= 100:
                rel, confidence, reason = "same_location", 0.88, f"Locations are approximately {distance:.1f} km apart."
        if not rel and event["category"] and event["category"] == other["category"] and event["country_code"] == other["country_code"]:
            rel, confidence, reason = "same_category", 0.78, "Both events share country and category."
        if not rel and event["country_code"] and event["country_code"] == other["country_code"]:
            rel, confidence, reason = "same_country", 0.65, "Both events are attributed to the same country."
        if rel:
            relationships.append({"event_id": other["id"], "relationship": rel,
                                  "confidence": confidence, "reason": reason,
                                  "title": other["title"], "category": other["category"],
                                  "country": other["country"], "event_time": to_iso(other["event_time"])})
    return relationships[:20]


def historical_stats(conn, start, end, country=None, region_codes=None, category=None):
    conditions = ["julianday(COALESCE(e.event_time, e.created_at)) >= julianday(?)",
                  "julianday(COALESCE(e.event_time, e.created_at)) < julianday(?)"]
    params = [start, end]
    if country:
        conditions.append("e.country_code = ?")
        params.append(country)
    if region_codes:
        conditions.append("e.country_code IN (%s)" % ",".join("?" * len(region_codes)))
        params.extend(region_codes)
    if category:
        conditions.append("e.category = ?")
        params.append(category)
    where = " AND ".join(conditions)
    summary = conn.execute(
        f"""SELECT COUNT(*) events, COALESCE(SUM(e.article_count),0) articles,
                   COALESCE(AVG(e.importance),0) average_importance,
                   COALESCE(AVG(e.confidence),0) average_confidence,
                   COUNT(DISTINCT e.country_code) countries,
                   COUNT(CASE WHEN e.importance >= 8 THEN 1 END) major_events
            FROM events e WHERE {where}""", params).fetchone()
    categories = conn.execute(
        f"SELECT e.category, COUNT(*) count FROM events e WHERE {where} GROUP BY e.category ORDER BY count DESC", params).fetchall()
    countries = conn.execute(
        f"SELECT e.country_code, e.country, COUNT(*) count FROM events e WHERE {where} GROUP BY e.country_code, e.country ORDER BY count DESC LIMIT 20", params).fetchall()
    return {"summary": dict(summary), "categories": [dict(x) for x in categories],
            "countries": [dict(x) for x in countries]}


def compare_periods(conn, period_a, period_b, scope=None):
    scope = scope or {}
    a = historical_stats(conn, period_a["start"], period_a["end"], scope.get("country"), scope.get("region_codes"), scope.get("category"))
    b = historical_stats(conn, period_b["start"], period_b["end"], scope.get("country"), scope.get("region_codes"), scope.get("category"))
    def delta(key):
        return (b["summary"].get(key) or 0) - (a["summary"].get(key) or 0)
    return {
        "period_a": a, "period_b": b,
        "summary": {"events_change": delta("events"), "articles_change": delta("articles"),
                    "major_events_change": delta("major_events"),
                    "average_importance_change": round(delta("average_importance"), 3),
                    "average_confidence_change": round(delta("average_confidence"), 3)},
        "category_changes": _merge_deltas(a["categories"], b["categories"], "category"),
        "country_changes": _merge_deltas(a["countries"], b["countries"], "country_code"),
    }


def _merge_deltas(a, b, key):
    left = {x[key]: x["count"] for x in a}
    right = {x[key]: x["count"] for x in b}
    return [{"key": k, "before": left.get(k, 0), "after": right.get(k, 0), "change": right.get(k, 0)-left.get(k, 0)}
            for k in sorted(set(left)|set(right), key=lambda x: -(right.get(x, 0)))]


def event_momentum(conn, event_id):
    rows = event_articles(conn, event_id)
    if len(rows) < 2:
        return {"state": "insufficient_data", "report_counts": [], "message": "At least two reports are required."}
    buckets = Counter()
    for row in rows:
        ts = parse_timestamp(row["published_at"]) or parse_timestamp(row["event_time"])
        if ts:
            buckets[ts.strftime("%Y-%m-%d %H:00")] += 1
    counts = list(buckets.values())
    if len(counts) < 2:
        state = "insufficient_data"
    elif counts[-1] > counts[0]:
        state = "increasing"
    elif counts[-1] < counts[0]:
        state = "declining"
    else:
        state = "stable"
    return {"state": state, "report_counts": [{"timestamp": k, "count": v} for k, v in sorted(buckets.items())],
            "message": f"Reporting activity is {state} during the observed period."}


def event_history(conn, event_id):
    timeline = build_timeline(conn, event_id)
    changes, claims = detect_changes(conn, event_id)
    diversity = source_diversity(conn, event_id)
    momentum = event_momentum(conn, event_id)
    relationships = ensure_relationships(conn, event_id)
    for item in timeline:
        item["changes"] = [c for c in changes if c.get("article_id") == item["article_id"]]
    return {"event_id": event_id, "timeline": timeline, "changes": changes,
            "claims": claims, "conflicting_reports": any(c["type"] == "conflicting_information" for c in changes),
            "source_diversity": diversity, "momentum": momentum,
            "related_events": relationships}
