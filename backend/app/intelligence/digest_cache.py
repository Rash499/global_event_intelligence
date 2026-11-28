"""SQLite-backed cache for scheduler-precomputed heavy API digests."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..database.db import get_connection, write_connection


def read_snapshot(key: str, *, max_age_seconds: int = 900, now: datetime | None = None) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT payload,generated_at FROM digest_snapshots WHERE snapshot_key=?", (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        generated = datetime.fromisoformat(row["generated_at"].replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        age = max(0, int((current - generated.astimezone(timezone.utc)).total_seconds()))
        if age > max_age_seconds:
            return None
        payload = json.loads(row["payload"])
        if isinstance(payload, dict):
            payload["cache_age_seconds"] = age
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def write_snapshot(key: str, payload: dict, *, generated_at: datetime | None = None) -> None:
    stamp = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    stored = {name: value for name, value in payload.items() if name != "cache_age_seconds"}
    with write_connection() as conn:
        conn.execute("""
            INSERT INTO digest_snapshots(snapshot_key,payload,generated_at) VALUES(?,?,?)
            ON CONFLICT(snapshot_key) DO UPDATE SET payload=excluded.payload,generated_at=excluded.generated_at
        """, (key, json.dumps(stored, default=str), stamp))


def invalidate_snapshots() -> None:
    with write_connection() as conn:
        conn.execute("DELETE FROM digest_snapshots")
