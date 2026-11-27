"""Alert rule evaluation.

Rules live in ``alert_rules``; triggered alerts in ``alerts``.  Evaluation runs
after ingestion and on demand, is idempotent (``UNIQUE(rule_id, event_id)``) and
records *why* a rule fired so every alert is explainable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..database.db import write_connection

logger = logging.getLogger(__name__)


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
        magnitude = None
        if raw:
            try:
                magnitude = json.loads(raw).get("magnitude")
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
        conn_hint = event.get("_entity_names") or ""
        if entity not in conn_hint.lower():
            return False, []
        reasons.append(f"Mentions entity “{rule['entity']}”")

    if not reasons:
        reasons.append("Rule matched the event's geographic and category scope.")

    return True, reasons


def evaluate_all_rules(limit: int = 400) -> int:
    """Evaluate every enabled rule against recent events. Returns alerts created."""
    now_iso = datetime.now(timezone.utc).isoformat()
    created = 0
    with write_connection() as conn:
        rules = [dict(r) for r in conn.execute(
            "SELECT * FROM alert_rules WHERE enabled = 1"
        ).fetchall()]
        if not rules:
            return 0

        events = [dict(r) for r in conn.execute(
            """
            SELECT id, title, summary, category, subcategory, country_code, severity,
                   confidence, event_state, priority_score, data_sources,
                   occurred_at, event_time
            FROM events
            WHERE julianday(COALESCE(occurred_at, event_time, created_at))
                  >= julianday('now', '-7 days')
            ORDER BY COALESCE(occurred_at, event_time) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()]

        entity_map: dict[int, list[str]] = {}
        for row in conn.execute(
            """
            SELECT m.event_id, e.name FROM event_entity_mentions m
            JOIN entities e ON e.id = m.entity_id
            """
        ).fetchall():
            entity_map.setdefault(row["event_id"], []).append(row["name"])

        for rule in rules:
            for event in events:
                event["_entity_names"] = " ".join(entity_map.get(event["id"], []))
                matched, reasons = _matches(rule, event)
                if not matched:
                    continue
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO alerts (
                        rule_id, event_id, triggered_at, status, severity, confidence,
                        title, reason, evidence
                    ) VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?)
                    """,
                    (
                        rule["id"],
                        event["id"],
                        now_iso,
                        event.get("severity"),
                        event.get("confidence"),
                        event.get("title"),
                        rule.get("name"),
                        json.dumps({"reasons": reasons, "rule": rule.get("name")}),
                    ),
                )
                if cursor.rowcount:
                    created += 1
            conn.execute(
                "UPDATE alert_rules SET last_evaluated_at = ? WHERE id = ?",
                (now_iso, rule["id"]),
            )
    return created
