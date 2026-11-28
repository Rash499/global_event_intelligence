"""Transparent country indicator scoring over stored event observations."""
from __future__ import annotations

import json
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parents[1] / "data" / "country_baselines.json"


def load_baselines() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def risk_level(score: float) -> str:
    return "Critical" if score >= 81 else "High" if score >= 66 else "Elevated" if score >= 51 else "Normal" if score >= 31 else "Low"


def _score(count: int, severity_values: list[float], *, unit: float = 12.0) -> float:
    if not count:
        return 0.0
    mean_severity = sum(severity_values) / len(severity_values) if severity_values else 0.0
    return round(min(100.0, count * unit + mean_severity * 4.0), 2)


def calculate_country_risk(country_code: str, events: list[dict], article_count: int, publisher_count: int, baselines: dict | None = None) -> dict:
    data = baselines or load_baselines()
    table = data.get("countries", {})
    baseline = float(table.get(country_code, data.get("default", 35)))
    baseline_source = "curated_static" if country_code in table else "fallback_static_default"
    unrest, conflict, security, information = [], [], [], []
    boosts = {"usgs_earthquakes": 0.0, "firms_wildfires": 0.0, "disasters": 0.0, "humanitarian": 0.0, "outbreaks": 0.0}
    counts = {key: 0 for key in boosts}
    for event in events:
        category = (event.get("category") or "").lower()
        subcategory = (event.get("subcategory") or "").lower()
        title = (event.get("title") or "").lower()
        provider_keys = str(event.get("provider_keys") or "").lower()
        severity = float(event.get("severity") or 0)
        if category == "protest_unrest" or any(term in subcategory + " " + title for term in ("protest", "riot", "unrest")):
            unrest.append(severity)
        if category in {"armed_conflict", "conflict"} or any(term in subcategory + " " + title for term in ("airstrike", "armed clash", "shelling", "fatalit", "killed in attack")):
            conflict.append(severity)
        if category in {"security", "military", "transportation"} or any(term in subcategory + " " + title for term in ("military", "airspace", "travel advisory", "security alert")):
            security.append(severity)
        if event.get("category"):
            information.append(severity)
        if "usgs" in provider_keys:
            counts["usgs_earthquakes"] += 1
        if "firms" in provider_keys:
            counts["firms_wildfires"] += 1
        if "gdacs" in provider_keys or "eonet" in provider_keys:
            counts["disasters"] += 1
        if "reliefweb" in provider_keys:
            counts["humanitarian"] += 1
        if "who" in provider_keys:
            counts["outbreaks"] += 1
    components = {
        "unrest": _score(len(unrest), unrest, unit=15),
        "conflict": _score(len(conflict), conflict, unit=18),
        "security": _score(len(security), security, unit=14),
        "information": round(min(100.0, article_count * 2.0 + min(20, publisher_count * 2.0) + len(information) * 3.0), 2),
    }
    event_score = round(0.25 * components["unrest"] + 0.30 * components["conflict"] + 0.20 * components["security"] + 0.25 * components["information"], 2)
    caps = {"usgs_earthquakes": 8, "firms_wildfires": 8, "disasters": 8, "humanitarian": 6, "outbreaks": 6}
    for key, cap in caps.items():
        boosts[key] = min(cap, counts[key] * 2.0)
    combined_before_adjustments = 0.40 * baseline + 0.60 * event_score
    floors_applied = []  # Conflict-history and travel-advisory providers are not yet registered.
    total_boost = sum(boosts.values())
    combined = max(0.0, min(100.0, combined_before_adjustments + total_boost))
    level = risk_level(combined)
    coverage = "none" if article_count == 0 and not events else "sparse" if article_count < 5 else "partial" if article_count < 25 else "good"
    missing = []
    if not events:
        missing.append("classified event inputs")
    if article_count == 0:
        missing.append("news article coverage")
    return {
        "score": round(combined, 2), "level": level,
        "formula": "clamp(0.40 × baseline + 0.60 × eventScore + capped provider boosts + applicable floors, 0, 100)",
        "baseline": {"score": baseline, "source": baseline_source},
        "event_score": event_score, "components": components,
        "weights": {"baseline": 0.40, "event_score": 0.60, "unrest": 0.25, "conflict": 0.30, "security": 0.20, "information": 0.25},
        "boosts": {key: {"score": value, "cap": caps[key], "observations": counts[key]} for key, value in boosts.items()},
        "floors_applied": floors_applied,
        "coverage": {"level": coverage, "articles": article_count, "publishers": publisher_count, "missing_inputs": missing, "warning": "Sparse or absent reporting is a data gap and must not be interpreted as calm conditions." if missing or coverage in {"none", "sparse"} else None},
        "limitations": ["Inputs reflect ingested and classified events, not complete ground truth.", "The curated static baseline is a coarse context value.", "Boosts are additive, capped, and can be absent when provider data is unavailable.", "This score is descriptive and not predictive."],
    }
