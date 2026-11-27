"""Operational priority: *how urgently should this event be looked at?*

Priority is a separate measurement from severity (how bad it is) and confidence
(how well we know).  It combines severity, confidence, recency, escalation and
watchlist relevance, and it is exposed with its own explanation so the UI never
presents an unexplained composite score.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .normalize_time import parse_timestamp

PRIORITY_LEVELS = (
    (8.0, "immediate"),
    (6.0, "elevated"),
    (4.0, "watch"),
    (0.0, "routine"),
)

ESCALATION_BONUS = {
    "escalating": 1.2,
    "increasing": 0.8,
    "stable": 0.0,
    "de-escalating": -0.6,
    "declining": -0.6,
}


def priority_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    for threshold, label in PRIORITY_LEVELS:
        if score >= threshold:
            return label
    return "routine"


def _hours_since(value: str | None) -> float | None:
    parsed = parse_timestamp(value)
    if not parsed:
        return None
    now = datetime.now(timezone.utc)
    return max(0.0, (now - parsed).total_seconds() / 3600)


def assess_priority(
    *,
    severity: float | None,
    confidence: float | None,
    occurred_at: str | None = None,
    event_state: str | None = None,
    escalation_trend: str | None = None,
    watchlist_match: bool = False,
) -> dict:
    components: list[dict] = []

    severity_value = severity if severity is not None else None
    if severity_value is not None:
        components.append(
            {
                "factor": "severity",
                "value": round(severity_value / 10.0, 3),
                "weight": 0.40,
                "evidence": f"Severity score {severity_value}/10",
            }
        )

    if confidence is not None:
        components.append(
            {
                "factor": "confidence",
                "value": round(confidence, 3),
                "weight": 0.20,
                "evidence": f"Intelligence confidence {round(confidence * 100)}%",
            }
        )

    hours = _hours_since(occurred_at)
    if hours is not None:
        # Half-life of 24h: a three-day-old event has a third of the freshness of
        # a new one.
        recency = 0.5 ** (hours / 24.0)
        components.append(
            {
                "factor": "recency",
                "value": round(recency, 3),
                "weight": 0.20,
                "evidence": (
                    f"Reported {hours:.1f}h ago"
                    if hours < 48
                    else f"Reported {hours / 24:.1f} days ago"
                ),
            }
        )

    trend = (escalation_trend or event_state or "").lower()
    if trend in ESCALATION_BONUS:
        bonus = ESCALATION_BONUS[trend]
        components.append(
            {
                "factor": "escalation",
                "value": round((bonus + 1.5) / 3.0, 3),
                "weight": 0.20,
                "evidence": f"Event trend is `{trend}`.",
            }
        )

    if watchlist_match:
        components.append(
            {
                "factor": "watchlist",
                "value": 1.0,
                "weight": 0.10,
                "evidence": "Matches an active monitoring watchlist.",
            }
        )

    if not components:
        return {
            "score": None,
            "label": "unknown",
            "components": [],
            "methodology": "Insufficient information to prioritise this event.",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    total_weight = sum(c["weight"] for c in components)
    score = sum(c["value"] * c["weight"] for c in components) / total_weight
    score = round(max(0.0, min(10.0, score * 10.0)), 2)

    return {
        "score": score,
        "label": priority_label(score),
        "components": [
            {**c, "contribution": round(c["value"] * c["weight"] / total_weight * 10, 3)}
            for c in components
        ],
        "methodology": (
            "Weighted mix of severity (40%), intelligence confidence (20%), "
            "recency with a 24-hour half-life (20%), escalation trend (20%) and "
            "watchlist relevance where applicable."
        ),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
