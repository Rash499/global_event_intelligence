"""Explainable alert rules with deterministic noise-control gates."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from ..database.db import write_connection

logger = logging.getLogger(__name__)


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def alert_gate_decision(event: dict, *, now: datetime, last_event_alert_at: datetime | None = None,
                        last_global_alert_at: datetime | None = None, last_global_severity: float | None = None,
                        sensitivity: str = "critical_and_high", source_tier="undeclared",
                        has_news_source: bool = False, story_phase: str | None = None) -> tuple[bool, str]:
    """Return (allowed, reason); injectable times make each gate hermetic."""
    now = now.astimezone(timezone.utc)
    occurred = _parse_time(event.get("occurred_at") or event.get("event_time") or event.get("created_at"))
    if occurred is not None and now - occurred > timedelta(minutes=15):
        return False, "recency_gate"
    importance = event.get("importance_score")
    if importance is None:
        importance = float(event.get("importance") or event.get("severity") or 0) * 10
    if float(importance) < 30:
        return False, "importance_floor"
    severity = float(event.get("severity") or 0)
    critical = severity >= 8.5
    high = severity >= 6.5
    if sensitivity == "critical_only" and not critical:
        return False, "user_sensitivity"
    if not high:
        return False, "severity_floor"
    if has_news_source and (not str(source_tier).isdigit() or int(source_tier) >= 3):
        method = str(event.get("classification_method") or "").lower()
        non_keyword_classifier = method in {"ai_assisted", "ml", "llm", "ollama"} and not event.get("classification_is_keyword")
        if not non_keyword_classifier:
            return False, "source_tier_gate"
    phase = (story_phase or event.get("story_phase") or event.get("event_state") or "").lower()
    if phase in {"sustained", "fading"}:
        return False, "story_phase_gate"
    if last_event_alert_at and now - last_event_alert_at < timedelta(minutes=30):
        return False, "event_dedup"
    if last_global_alert_at and now - last_global_alert_at < timedelta(seconds=60):
        previous_is_high = last_global_severity is not None and 6.5 <= float(last_global_severity) < 8.5
        if not (critical and previous_is_high):
            return False, "global_cooldown"
    return True, "allowed"


def _matches(rule: dict, event: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if rule.get("country_code") and (event.get("country_code") or "").upper() != rule["country_code"].upper():
        return False, []
    if rule.get("category") and event.get("category") != rule["category"]:
        return False, []
    if rule.get("subcategory") and event.get("subcategory") != rule["subcategory"]:
        return False, []
    if rule.get("event_state") and event.get("event_state") != rule["event_state"]:
        return False, []
    if rule.get("min_severity") is not None:
        severity = event.get("severity")
        if severity is None or float(severity) < float(rule["min_severity"]):
            return False, []
        reasons.append(f"Severity {round(float(severity), 1)} ≥ {rule['min_severity']}")
    if rule.get("min_confidence") is not None:
        confidence = event.get("confidence")
        if confidence is None or float(confidence) < float(rule["min_confidence"]):
            return False, []
        reasons.append(f"Confidence {round(float(confidence) * 100)}% ≥ {round(float(rule['min_confidence']) * 100)}%")
    if rule.get("min_magnitude") is not None:
        raw = event.get("data_sources")
        try:
            magnitude = json.loads(raw).get("magnitude") if raw else None
        except (TypeError, ValueError, AttributeError):
            magnitude = None
        if magnitude is None or float(magnitude) < float(rule["min_magnitude"]):
            return False, []
        reasons.append(f"Magnitude {magnitude} ≥ {rule['min_magnitude']}")
    if rule.get("keywords"):
        text = f"{event.get('title') or ''} {event.get('summary') or ''}".lower()
        keywords = [k.strip().lower() for k in str(rule["keywords"]).split(",") if k.strip()]
        hits = [k for k in keywords if k in text]
        if not hits:
            return False, []
        reasons.append("Matched keywords: " + ", ".join(hits))
    if rule.get("entity"):
        entity = str(rule["entity"]).lower()
        if entity not in str(event.get("_entity_names") or "").lower():
            return False, []
        reasons.append(f"Mentions entity “{rule['entity']}”")
    if not reasons:
        reasons.append("Rule matched the event's geographic and category scope.")
    return True, reasons


def evaluate_all_rules(limit: int = 400, *, now: datetime | None = None) -> int:
    """Evaluate enabled rules against recent, eligible events."""
    now_dt = now or datetime.now(timezone.utc)
    now_dt = now_dt.astimezone(timezone.utc)
    now_iso = now_dt.isoformat()
    created = 0
    with write_connection() as conn:
        rules = [dict(r) for r in conn.execute("SELECT * FROM alert_rules WHERE enabled = 1").fetchall()]
        events = [dict(r) for r in conn.execute("""
            SELECT id, title, summary, category, subcategory, country_code, severity,
                   confidence, event_state, escalation_trend, classification_method,
                   classification_confidence, priority_score, importance_score, importance,
                   data_sources, occurred_at, event_time, created_at,
                   (SELECT COUNT(*) FROM event_articles ea WHERE ea.event_id=e.id) AS news_source_count,
                   (SELECT MIN(a.source_tier) FROM event_articles ea JOIN articles a ON a.id=ea.article_id WHERE ea.event_id=e.id) AS lowest_source_tier
            FROM events e
            WHERE julianday(COALESCE(occurred_at, event_time, created_at)) >= julianday(?)
            ORDER BY COALESCE(occurred_at, event_time) DESC LIMIT ?
            """, ((now_dt - timedelta(days=7)).isoformat(), limit)).fetchall()]
        entity_map: dict[int, list[str]] = {}
        for row in conn.execute("SELECT m.event_id, e.name FROM event_entity_mentions m JOIN entities e ON e.id=m.entity_id").fetchall():
            entity_map.setdefault(row["event_id"], []).append(row["name"])
        latest = conn.execute("SELECT triggered_at, severity FROM alerts ORDER BY triggered_at DESC LIMIT 1").fetchone()
        last_global_at = _parse_time(latest["triggered_at"]) if latest else None
        last_global_severity = latest["severity"] if latest else None
        for rule in rules:
            pref = conn.execute("SELECT sensitivity FROM user_alert_preferences WHERE user_id=?", (rule.get("user_id"),)).fetchone() if rule.get("user_id") else None
            sensitivity = pref["sensitivity"] if pref else "critical_and_high"
            for event in events:
                event["_entity_names"] = " ".join(entity_map.get(event["id"], []))
                matched, reasons = _matches(rule, event)
                if not matched:
                    continue
                suppression = conn.execute("SELECT suppressed_until FROM alert_event_suppressions WHERE event_id=?", (event["id"],)).fetchone()
                event_alert_at = _parse_time(suppression["suppressed_until"]) - timedelta(minutes=30) if suppression else None
                allowed, gate = alert_gate_decision(
                    event, now=now_dt, last_event_alert_at=event_alert_at,
                    last_global_alert_at=last_global_at, last_global_severity=last_global_severity,
                    sensitivity=sensitivity, source_tier=event.get("lowest_source_tier", "undeclared"),
                    has_news_source=bool(event.get("news_source_count")),
                    story_phase=event.get("escalation_trend"),
                )
                if not allowed:
                    continue
                reasons.append(f"Noise gate result: {gate}")
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO alerts (rule_id, event_id, triggered_at, status, severity, confidence, title, reason, evidence)
                    VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?)
                    """, (rule["id"], event["id"], now_iso, event.get("severity"), event.get("confidence"), event.get("title"), rule.get("name"), json.dumps({"reasons": reasons, "rule": rule.get("name")})))
                if cursor.rowcount:
                    created += 1
                    conn.execute("INSERT INTO alert_event_suppressions(event_id,suppressed_until,severity,created_at) VALUES(?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET suppressed_until=excluded.suppressed_until,severity=excluded.severity,created_at=excluded.created_at", (event["id"], (now_dt + timedelta(minutes=30)).isoformat(), "critical" if float(event.get("severity") or 0) >= 8.5 else "high", now_iso))
                    last_global_at, last_global_severity = now_dt, event.get("severity")
            conn.execute("UPDATE alert_rules SET last_evaluated_at=? WHERE id=?", (now_iso, rule["id"]))

        # Spatial convergence is a system signal, linked to its newest sample
        # event so it can use the same recency, severity and cooldown gates.
        from ..intelligence.convergence import spatial_convergence_cells
        for cell in spatial_convergence_cells(conn, now=now_dt, window_hours=24):
            representative = cell["representative_event"]
            event_id = representative["id"]
            suppression = conn.execute("SELECT suppressed_until FROM alert_event_suppressions WHERE event_id=?", (event_id,)).fetchone()
            event_alert_at = _parse_time(suppression["suppressed_until"]) - timedelta(minutes=30) if suppression else None
            source = conn.execute("SELECT COUNT(*) AS n,MIN(a.source_tier) AS tier FROM event_articles ea JOIN articles a ON a.id=ea.article_id WHERE ea.event_id=?", (event_id,)).fetchone()
            gate_event = {**representative, "severity": 9 if cell["severity"] == "critical" else 7, "importance_score": max(float(representative.get("importance_score") or 0), float(cell["score"]))}
            allowed, gate = alert_gate_decision(gate_event, now=now_dt, last_event_alert_at=event_alert_at, last_global_alert_at=last_global_at, last_global_severity=last_global_severity, source_tier=source["tier"] or "undeclared", has_news_source=bool(source["n"]))
            if not allowed:
                continue
            country_name = (cell.get("nearest_country") or {}).get("name") or "unknown region"
            title = f"Spatial convergence near {country_name}"
            conn.execute("""
                INSERT INTO alerts(rule_id,event_id,triggered_at,status,severity,confidence,title,reason,evidence)
                VALUES(NULL,?,?, 'new', ?, ?, ?, 'Spatial convergence', ?)
            """, (event_id, now_iso, gate_event["severity"], representative.get("confidence"), title, json.dumps({"reasons":["Three or more distinct event categories in one 1-degree cell during the last 24 hours", f"Noise gate result: {gate}"], "cell":cell["cell"], "score":cell["score"], "severity":cell["severity"], "event_types":cell["event_types"], "sample_event_ids":cell["sample_event_ids"], "nearest_country":cell.get("nearest_country")})))
            conn.execute("INSERT INTO alert_event_suppressions(event_id,suppressed_until,severity,created_at) VALUES(?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET suppressed_until=excluded.suppressed_until,severity=excluded.severity,created_at=excluded.created_at", (event_id, (now_dt+timedelta(minutes=30)).isoformat(), cell["severity"], now_iso))
            created += 1
            last_global_at, last_global_severity = now_dt, gate_event["severity"]
    return created
