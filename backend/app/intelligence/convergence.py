"""Spatial grouping over geolocated event records; no external geocoder used."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .geolocation import COUNTRY_BY_CODE


def _nearest_country(latitude: float, longitude: float) -> dict | None:
    best = None
    best_distance = float("inf")
    for item in COUNTRY_BY_CODE.values():
        distance = (latitude - item["lat"]) ** 2 + (longitude - item["lon"]) ** 2
        if distance < best_distance:
            best, best_distance = item, distance
    if not best:
        return None
    return {"country_code": best["code"], "name": best["name"], "distance_degrees": round(math.sqrt(best_distance), 2)}


def spatial_convergence_cells(conn, *, now: datetime | None = None, window_hours: int = 24) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    start = current - timedelta(hours=window_hours)
    rows = conn.execute("""
        SELECT id,title,category,subcategory,country,country_code,latitude,longitude,severity,
               COALESCE(occurred_at,event_time,created_at) AS occurred_at,
               classification_method,importance_score,importance
        FROM events
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND category IS NOT NULL
          AND julianday(COALESCE(occurred_at,event_time,created_at)) >= julianday(?)
        ORDER BY COALESCE(occurred_at,event_time,created_at) DESC,id DESC
    """, (start.isoformat(),)).fetchall()
    bins: dict[tuple[int,int], list[dict]] = {}
    for row in rows:
        event = dict(row)
        key = (math.floor(float(event["latitude"])), math.floor(float(event["longitude"])))
        bins.setdefault(key, []).append(event)
    output = []
    for (lat_bin, lon_bin), events in bins.items():
        types = sorted({event["category"] for event in events})
        if len(types) < 3:
            continue
        score = 25 * len(types) + min(25, 2 * len(events))
        center = (lat_bin + 0.5, lon_bin + 0.5)
        nearest = _nearest_country(*center)
        output.append({
            "cell": {"latitude_bin": lat_bin, "longitude_bin": lon_bin, "center_latitude": center[0], "center_longitude": center[1]},
            "window_hours": window_hours,
            "event_count": len(events),
            "distinct_event_types": len(types),
            "event_types": types,
            "score": score,
            "severity": "critical" if len(types) >= 4 or score >= 90 else "high",
            "nearest_country": nearest,
            "sample_event_ids": [event["id"] for event in events[:12]],
            "representative_event": events[0],
            "events": [{"id": event["id"], "title": event["title"], "category": event["category"], "severity": event["severity"], "occurred_at": event["occurred_at"]} for event in events[:8]],
        })
    output.sort(key=lambda item: (-item["score"], -item["event_count"], item["cell"]["latitude_bin"], item["cell"]["longitude_bin"]))
    return output
