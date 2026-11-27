"""Emerging-event / anomaly detection over rolling baselines.

Design constraints that keep this trustworthy:

* activity is measured on **events**, not articles, so one publisher repeating
  itself does not create an anomaly;
* sources are deduplicated per event before counting, and a minimum number of
  independent sources is required;
* the baseline is the same metric over the preceding comparable windows, so a
  normally busy region is not flagged for being busy;
* collection outages are accounted for: if a provider has not collected
  recently, the observed window is marked as coverage-limited and suppressed;
* every anomaly carries the observed value, the baseline, the deviation and the
  sample events that produced it, and is stored so the UI can show history.

No predictive claim is made anywhere.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Minimum evidence before a deviation is reportable.
MIN_OBSERVED_EVENTS = 3
MIN_BASELINE_EVENTS = 3
# Z-like threshold on the ratio to the baseline; deliberately conservative.
DEVIATION_THRESHOLD = 2.0
MAX_ANOMALIES_PER_RUN = 25


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _window_counts(conn, column: str, start: str, end: str, key: str | None = None) -> dict:
    if key:
        sql = f"""
            SELECT {column} AS k, COUNT(*) AS c
            FROM events
            WHERE julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
              AND julianday(COALESCE(occurred_at, event_time, created_at)) < julianday(?)
              AND {column} IS NOT NULL
            GROUP BY {column}
        """
        rows = conn.execute(sql, (start, end)).fetchall()
    else:
        sql = f"""
            SELECT {column} AS k, COUNT(*) AS c
            FROM events
            WHERE julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
              AND julianday(COALESCE(occurred_at, event_time, created_at)) < julianday(?)
              AND {column} IS NOT NULL
            GROUP BY {column}
        """
        rows = conn.execute(sql, (start, end)).fetchall()
    return {row["k"]: row["c"] for row in rows}


def _coverage_is_adequate(conn, start: str) -> tuple[bool, str]:
    """Guard against flagging an anomaly that is really a collection outage."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS runs,
               SUM(CASE WHEN status IN ('healthy','degraded') THEN 1 ELSE 0 END) AS ok
        FROM collection_runs
        WHERE julianday(started_at) >= julianday(?)
        """,
        (start,),
    ).fetchone()
    runs = row["runs"] or 0
    ok = row["ok"] or 0
    if runs == 0:
        return False, "No collection runs were recorded in the observed window."
    if ok == 0:
        return False, "Every collection run in the observed window failed."
    return True, f"{ok}/{runs} collection runs succeeded in the observed window."


def _sample_events(conn, dimension: str, value: str, start: str, end: str, limit: int = 8) -> list[int]:
    column = {"category": "category", "country": "country_code", "subcategory": "subcategory"}.get(
        dimension, "category"
    )
    rows = conn.execute(
        f"""
        SELECT id FROM events
        WHERE {column} = ?
          AND julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
          AND julianday(COALESCE(occurred_at, event_time, created_at)) < julianday(?)
        ORDER BY COALESCE(severity, 0) DESC, id DESC
        LIMIT ?
        """,
        (value, start, end, limit),
    ).fetchall()
    return [row["id"] for row in rows]


def _independent_source_count(conn, event_ids: list[int]) -> int:
    if not event_ids:
        return 0
    placeholders = ",".join("?" for _ in event_ids)
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT a.publisher_domain) AS c
        FROM articles a
        JOIN event_articles ea ON ea.article_id = a.id
        WHERE ea.event_id IN ({placeholders})
        """,
        event_ids,
    ).fetchone()
    return row["c"] or 0


def detect_anomalies(conn, window_hours: int = 24, store: bool = True) -> list[dict]:
    """Detect significant activity changes across categories and countries."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)
    baseline_start = now - timedelta(hours=window_hours * 8)

    adequate, coverage_note = _coverage_is_adequate(conn, _iso(window_start))
    if not adequate and conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] > 0:
        logger.info("[ANOMALY] skipping detection: %s", coverage_note)
        return []

    found: list[dict] = []
    for dimension, column in (("category", "category"), ("country", "country_code"), ("subcategory", "subcategory")):
        observed = _window_counts(conn, column, _iso(window_start), _iso(now))
        baseline = _window_counts(conn, column, _iso(baseline_start), _iso(window_start))

        for key, count in observed.items():
            if not key or count < MIN_OBSERVED_EVENTS:
                continue
            history = baseline.get(key, 0)
            # Baseline is per-window (7 preceding windows of equal length).
            expected = history / 7.0
            if history < MIN_BASELINE_EVENTS:
                continue

            # Poisson-ish significance: require the observed count to exceed the
            # expected value by more than the threshold AND by a margin that the
            # sampling noise cannot explain.
            ratio = count / max(expected, 0.5)
            if ratio < DEVIATION_THRESHOLD:
                continue
            if count < expected + DEVIATION_THRESHOLD * math.sqrt(max(expected, 1.0)):
                continue

            samples = _sample_events(conn, dimension, key, _iso(window_start), _iso(now))
            independent = _independent_source_count(conn, samples)
            if independent < 2:
                # A single publisher repeating itself is not an emerging event.
                continue

            confidence = min(0.95, 0.45 + 0.1 * independent + min(0.2, (ratio - DEVIATION_THRESHOLD) * 0.05))
            explanation = (
                f"{count} {dimension} events involving `{key}` were recorded in the last "
                f"{window_hours}h, against an expected {expected:.1f} based on the "
                f"preceding {(baseline_start and window_hours * 7)}h "
                f"({history} events across seven comparable windows). "
                f"{independent} independent publishers support these records. "
                f"{coverage_note}"
            )
            found.append(
                {
                    "dimension": dimension,
                    "key": str(key),
                    "window_hours": window_hours,
                    "observed": count,
                    "baseline": history,
                    "expected": round(expected, 2),
                    "deviation": round(ratio, 2),
                    "score": round(ratio * min(1.0, independent / 3), 2),
                    "independent_sources": independent,
                    "confidence": round(confidence, 3),
                    "explanation": explanation,
                    "sample_event_ids": samples,
                    "limitations": (
                        "Detected from collected reporting; changes in provider coverage "
                        "or collection outages can affect the observed count."
                    ),
                }
            )

    found.sort(key=lambda item: -item["score"])
    found = found[:MAX_ANOMALIES_PER_RUN]

    if store and found:
        from ..database.db import write_connection

        detected_at = _iso(now)
        with write_connection() as write_conn:
            for item in found:
                write_conn.execute(
                    """
                    INSERT OR IGNORE INTO anomalies (
                        detected_at, dimension, key, window_hours, observed, baseline,
                        expected, deviation, score, independent_sources, confidence,
                        explanation, sample_event_ids
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detected_at,
                        item["dimension"],
                        item["key"],
                        item["window_hours"],
                        item["observed"],
                        item["baseline"],
                        item["expected"],
                        item["deviation"],
                        item["score"],
                        item["independent_sources"],
                        item["confidence"],
                        item["explanation"] + " " + item["limitations"],
                        json.dumps(item["sample_event_ids"]),
                    ),
                )

    return found
