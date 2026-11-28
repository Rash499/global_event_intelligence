"""Explainable event ranking, kept separate from impact severity.

All tunable values live in ``IMPORTANCE_CONFIG`` so changes are reviewable and
unit-tested as one policy. The result is a descriptive ranking, not a forecast.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def importance_from_severity(severity: float | None, fallback: int = 5) -> int:
    if severity is None:
        return int(clamp(fallback, 1, 10))
    return int(clamp(round(float(severity)), 1, 10))


def score_event_importance(data: dict) -> int:
    """Legacy compatibility API: average the available evidence-backed fields."""
    severity = data.get("severity")
    if severity is not None:
        return importance_from_severity(float(severity))
    numeric = [float(data[key]) for key in ("human_impact", "physical_magnitude", "official_severity") if isinstance(data.get(key), (int, float))]
    if not numeric:
        return importance_from_severity(None)
    return importance_from_severity(sum(numeric) / len(numeric))


@dataclass(frozen=True)
class ImportanceConfig:
    """Documented v1 ranking weights; contributions are points on 0-100."""
    source_points: float = 2.5
    source_cap: int = 6
    entity_corroboration_points: float = 8.0
    source_tier_points: tuple[float, ...] = (9.0, 6.0, 3.0, 0.0)
    undeclared_tier_points: float = 0.0
    keyword_group_points: float = 5.0
    flashpoint_multiplier: float = 1.35
    recency_hours: float = 16.0
    recency_floor: float = 0.5
    financial_noise_multiplier: float = 0.35
    strong_classifier_confidence: float = 0.8


IMPORTANCE_CONFIG = ImportanceConfig()

KEYWORD_GROUPS: dict[str, tuple[str, ...]] = {
    "violence": ("killed", "fatalities", "attack", "massacre", "casualties", "shooting"),
    "military": ("military", "troops", "airstrike", "missile", "mobilization", "naval"),
    "unrest": ("protest", "riot", "demonstration", "strike", "civil unrest"),
    "diplomacy": ("ceasefire", "treaty", "summit", "negotiation", "diplomatic", "sanctions"),
    "crisis": ("emergency", "crisis", "evacuation", "outbreak", "famine", "disaster"),
    "flashpoint": ("border clash", "escalation", "flashpoint", "invasion", "cross-border"),
}
FINANCIAL_NOISE = ("stock market", "shares rise", "quarterly earnings", "profit outlook", "market rally", "price target")


def calculate_importance_score(event: dict, articles: list[dict], entities: list[str] | None = None, *, now: datetime | None = None) -> dict:
    """Return normalized importance ranking with inspectable components."""
    cfg = IMPORTANCE_CONFIG
    text = " ".join([str(event.get("title") or ""), str(event.get("summary") or "")] + [f"{a.get('title') or ''} {a.get('description') or ''}" for a in articles]).lower()
    source_domains = {str(a.get("publisher_domain") or a.get("publisher") or "").lower() for a in articles if a.get("publisher_domain") or a.get("publisher")}
    source_count = min(cfg.source_cap, len(source_domains))
    base = float(clamp(float(event.get("severity") or event.get("importance") or 5) * 10, 0, 100))
    source_bonus = max(0, source_count - 1) * cfg.source_points
    entity_values = entities or []
    entity_bonus = cfg.entity_corroboration_points if len(set(entity_values)) >= 2 else 0.0
    tiers = [a.get("source_tier", "undeclared") for a in articles]
    tier_values = []
    for tier in tiers:
        tier_values.append(cfg.source_tier_points[int(tier) - 1] if str(tier).isdigit() and 1 <= int(tier) <= 4 else cfg.undeclared_tier_points)
    tier_bonus = sum(tier_values) / len(tier_values) if tier_values else 0.0
    hits = [name for name, words in KEYWORD_GROUPS.items() if any(word in text for word in words)]
    keyword_bonus = cfg.keyword_group_points * len(hits)
    flashpoint = "flashpoint" in hits and bool(set(hits) & {"violence", "military", "unrest"})
    if flashpoint:
        keyword_bonus *= cfg.flashpoint_multiplier
    observed = event.get("occurred_at") or event.get("event_time") or event.get("created_at")
    age_hours = None
    recency = 1.0
    if observed:
        try:
            parsed = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, ((now or datetime.now(timezone.utc)) - parsed).total_seconds() / 3600)
            recency = max(cfg.recency_floor, 1.0 - min(age_hours, cfg.recency_hours) / (cfg.recency_hours * 2))
        except (ValueError, TypeError):
            pass
    classifier_confidence = float(event.get("classification_confidence") or 0)
    strong_classifier = classifier_confidence >= cfg.strong_classifier_confidence and event.get("classification_method") in {"ai_assisted", "llm", "ml"}
    financial_noise = any(term in text for term in FINANCIAL_NOISE)
    demoted = financial_noise and len(set(entity_values)) < 2 and not strong_classifier
    raw = base + source_bonus + entity_bonus + tier_bonus + keyword_bonus
    final = raw * recency * (cfg.financial_noise_multiplier if demoted else 1.0)
    return {
        "score": round(clamp(final, 0, 100), 2),
        "components": {"base": round(base, 2), "source_count": source_count, "source_bonus": round(source_bonus, 2), "entity_corroboration_bonus": entity_bonus, "source_tier_bonus": round(tier_bonus, 2), "keyword_groups": hits, "keyword_bonus": round(keyword_bonus, 2), "flashpoint_interaction": flashpoint, "recency_multiplier": round(recency, 3), "age_hours": round(age_hours, 2) if age_hours is not None else None, "financial_noise_demoted": demoted, "classifier_signal_strong": strong_classifier},
    }
