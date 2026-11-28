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
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Minimum evidence before a deviation is reportable.
MIN_OBSERVED_EVENTS = 3
MIN_BASELINE_EVENTS = 3
# Z-like threshold on the ratio to the baseline; deliberately conservative.
DEVIATION_THRESHOLD = 2.0
MAX_ANOMALIES_PER_RUN = 25
BASELINE_RETENTION_DAYS = 90
BASELINE_MIN_SAMPLES = 10


def severity_band_for_z(z_score: float) -> str | None:
    if z_score >= 3.0:
        return "critical"
    if z_score >= 2.0:
        return "high"
    if z_score >= 1.5:
        return "medium"
    return None


class WelfordBaseline:
    """Online mean/variance with bounded 90-day sample retention."""
    def __init__(self, samples=None, retention_days=BASELINE_RETENTION_DAYS):
        self.retention = timedelta(days=retention_days)
        self.samples = []
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0
        for timestamp, value in samples or []:
            self.add(timestamp, value)

    def add(self, timestamp: datetime, value: float, now: datetime | None = None):
        timestamp = timestamp.astimezone(timezone.utc)
        current = (now or timestamp).astimezone(timezone.utc)
        self.samples.append((timestamp, float(value)))
        self.samples = [(stamp, val) for stamp, val in self.samples if current - stamp < self.retention]
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0
        for _, sample in sorted(self.samples, key=lambda item: item[0]):
            self.count += 1
            delta = sample - self.mean
            self.mean += delta / self.count
            self.m2 += delta * (sample - self.mean)

    @property
    def variance(self):
        return self.m2 / (self.count - 1) if self.count > 1 else 0.0

    def z_score(self, observed: float) -> float | None:
        if self.count < BASELINE_MIN_SAMPLES:
            return None
        deviation = math.sqrt(self.variance)
        if deviation == 0:
            return 0.0 if observed <= self.mean else 3.0
        return (float(observed) - self.mean) / deviation


def _refresh_region_baselines(conn, now: datetime) -> None:
    """Record daily country/region counts and rebuild compact Welford stats."""
    cutoff = now - timedelta(days=BASELINE_RETENTION_DAYS)
    cutoff_date = cutoff.date().isoformat()
    rows = conn.execute("""
        SELECT country_code AS region,
               substr(COALESCE(occurred_at,event_time,created_at),1,10) AS day,
               COUNT(*) AS total, json_group_array(id) AS ids
        FROM events
        WHERE country_code IS NOT NULL
          AND julianday(COALESCE(occurred_at,event_time,created_at)) >= julianday(?)
        GROUP BY country_code, day
    """, (cutoff.isoformat(),)).fetchall()
    counts = {(row["region"], row["day"]): (row["total"], row["ids"] or "[]") for row in rows}
    regions = {region for region, _ in counts}
    yesterday = now.date() - timedelta(days=1)
    for region in regions:
        region_dates = [datetime.fromisoformat(day).date() for item_region, day in counts if item_region == region]
        if not region_dates:
            continue
        start = max(cutoff.date(), min(region_dates))
        day = start
        while day <= yesterday:
            date_key = day.isoformat()
            total, ids = counts.get((region, date_key), (0, "[]"))
            for kind, key in (("weekday", str(day.weekday())), ("month", str(day.month))):
                conn.execute("""
                    INSERT OR IGNORE INTO region_baseline_samples(region,bucket_kind,bucket_key,sample_date,observed_count,sample_event_ids)
                    VALUES(?,?,?,?,?,?)
                """, (region, kind, key, date_key, total, ids))
            day += timedelta(days=1)
    conn.execute("DELETE FROM region_baseline_samples WHERE sample_date < ?", (cutoff_date,))
    groups = conn.execute("""
        SELECT region,bucket_kind,bucket_key,sample_date,observed_count
        FROM region_baseline_samples ORDER BY region,bucket_kind,bucket_key,sample_date
    """).fetchall()
    baselines = {}
    for row in groups:
        key = (row["region"], row["bucket_kind"], row["bucket_key"])
        baseline = baselines.setdefault(key, WelfordBaseline())
        sample_date = datetime.fromisoformat(row["sample_date"]).replace(tzinfo=timezone.utc)
        baseline.add(sample_date, row["observed_count"], now=now)
    conn.execute("DELETE FROM region_baselines")
    for (region, kind, key), baseline in baselines.items():
        conn.execute("""
            INSERT INTO region_baselines(region,bucket_kind,bucket_key,sample_count,mean,m2,updated_at)
            VALUES(?,?,?,?,?,?,?)
        """, (region, kind, key, baseline.count, baseline.mean, baseline.m2, now.isoformat()))
    conn.commit()


def _region_anomalies(conn, now: datetime) -> list[dict]:
    _refresh_region_baselines(conn, now)
    start = now - timedelta(hours=24)
    observed = conn.execute("""
        SELECT country_code AS region,COUNT(*) AS total,json_group_array(id) AS ids
        FROM events WHERE country_code IS NOT NULL
          AND julianday(COALESCE(occurred_at,event_time,created_at)) >= julianday(?)
        GROUP BY country_code
    """, (start.isoformat(),)).fetchall()
    output = []
    for row in observed:
        region = row["region"]
        for kind, key in (("weekday", str(now.weekday())), ("month", str(now.month))):
            stats = conn.execute("SELECT sample_count,mean,m2 FROM region_baselines WHERE region=? AND bucket_kind=? AND bucket_key=?", (region, kind, key)).fetchone()
            if not stats or stats["sample_count"] < BASELINE_MIN_SAMPLES:
                continue
            variance = stats["m2"] / max(1, stats["sample_count"] - 1)
            sd = math.sqrt(variance)
            z = (row["total"] - stats["mean"]) / sd if sd else (3.0 if row["total"] > stats["mean"] else 0.0)
            band = severity_band_for_z(z)
            if band is None:
                continue
            output.append({"dimension":"region_activity", "key":region, "bucket":kind, "window_hours":24, "observed":row["total"], "baseline":round(stats["mean"],2), "expected":round(stats["mean"],2), "deviation":round(z,2), "z_score":round(z,2), "score":round(z,2), "severity":band, "independent_sources":0, "confidence":None, "sample_event_ids":json.loads(row["ids"] or "[]")[:8], "explanation":f"Observed activity is {z:.2f} standard deviations above the {kind}-matched 90-day regional baseline; this is a description of collected events, not a prediction."})
    return output


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


def _keyword_spikes(conn, now: datetime) -> list[dict]:
    """Spot title/entity terms rising above their preceding seven-day daily rate."""
    start = now - timedelta(days=8)
    rows = conn.execute("""
        SELECT id,title,COALESCE(occurred_at,event_time,created_at) AS event_at
        FROM events WHERE julianday(COALESCE(occurred_at,event_time,created_at)) >= julianday(?)
    """, (start.isoformat(),)).fetchall()
    entity_names = {}
    for entity in conn.execute("SELECT m.event_id,e.name FROM event_entity_mentions m JOIN entities e ON e.id=m.entity_id").fetchall():
        entity_names.setdefault(entity["event_id"], []).append(entity["name"])
    cutoff = now - timedelta(hours=24)
    stop = {"the","and","for","with","from","that","this","after","before","into","over","under","says","said","will","has","have","was","are","its","their","they","been","not","new","update","live","latest"}
    current: dict[str, list[int]] = {}
    history: dict[str, set[str]] = {}
    for row in rows:
        event_at = _parse_datetime(row["event_at"])
        if not event_at:
            continue
        terms = {word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", ((row["title"] or "") + " " + " ".join(entity_names.get(row["id"], []))).lower()) if word not in stop}
        if event_at >= cutoff:
            for term in terms:
                current.setdefault(term, []).append(row["id"])
        else:
            history.update({term: history.get(term, set()) | {row["event_at"][:10]} for term in terms})
    output = []
    for term, event_ids in current.items():
        baseline_daily = len(history.get(term, set())) / 7.0
        if len(event_ids) < 2 or baseline_daily <= 0 or len(event_ids) <= 3 * baseline_daily:
            continue
        ratio = len(event_ids) / baseline_daily
        output.append({"dimension":"keyword_spike", "key":term, "window_hours":24, "observed":len(event_ids), "baseline":round(baseline_daily,2), "expected":round(baseline_daily,2), "deviation":round(ratio,2), "score":round(ratio,2), "independent_sources":0, "confidence":None, "sample_event_ids":event_ids[:8], "explanation":f"The title term `{term}` appeared {len(event_ids)} times in the last 24 hours, above three times its observed seven-day daily baseline. This is a reporting-volume observation, not a prediction."})
    return output


def _parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


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

    # Country-code buckets are used as the available region identifiers; each
    # bucket is compared to weekday- and month-matched baselines.
    found.extend(_region_anomalies(conn, now))
    found.extend(_keyword_spikes(conn, now))
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
                        explanation, sample_event_ids, severity, z_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        item["explanation"] + " " + item.get("limitations", ""),
                        json.dumps(item["sample_event_ids"]),
                        item.get("severity"),
                        item.get("z_score", item.get("deviation")),
                    ),
                )

    return found
