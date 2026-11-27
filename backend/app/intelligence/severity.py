"""Severity assessment: *how serious is the reported event?*

Every factor is derived from evidence in the stored records.  Where a factor
cannot be established it is reported as ``unknown`` and excluded from the
weighted average (rather than silently defaulting to a middling number, which
would make every event look the same).

Returned payload::

    {
      "score": 6.4 | None,
      "label": "high",
      "components": [ {factor, value, weight, evidence, confidence} ],
      "missing_evidence": ["economic_impact"],
      "methodology": "...",
      "calculated_at": "..."
    }
"""

from __future__ import annotations

from datetime import datetime, timezone

LABELS = (
    (8.5, "critical"),
    (6.5, "high"),
    (4.5, "moderate"),
    (2.5, "low"),
    (0.0, "minimal"),
)

CATEGORY_BASELINES = {
    "natural_disaster": 6.0,
    "armed_conflict": 6.5,
    "terrorism_extremism": 6.5,
    "humanitarian": 5.5,
    "public_health": 5.0,
    "severe_weather": 4.5,
    "protest_unrest": 3.5,
    "energy_infrastructure": 4.5,
    "transportation": 4.0,
    "crime_public_safety": 3.5,
    "environmental": 4.0,
    "political_development": 3.5,
    "economic_financial": 3.5,
    "international_relations": 3.0,
    "cyber_technology": 3.0,
    "other": 2.0,
}

# Subtype adjustments: a magnitude-scaled earthquake is handled separately, but
# these refine the baseline with attested domain knowledge about typical impact.
SUBCATEGORY_MODIFIERS = {
    "earthquake": 1.0,
    "tsunami": 2.0,
    "tropical_cyclone": 1.0,
    "wildfire": 0.5,
    "flood": 0.5,
    "volcanic_activity": 0.5,
    "airstrike": 0.75,
    "missile_attack": 0.75,
    "armed_clash": 0.5,
    "shelling": 0.5,
    "terror_attack": 1.0,
    "disease_outbreak": 0.5,
    "pandemic_alert": 1.5,
    "cyber_attack": 0.25,
    "power_disruption": 0.25,
}

# Casualty thresholds -> (severity, narrative). Evidence-based bands used by
# humanitarian reporting; a single death is already material.
CASUALTY_BANDS = (
    (5000, 10.0, "Very large-scale loss of life reported"),
    (1000, 9.5, "Large-scale loss of life reported"),
    (500, 9.0, "Hundreds of deaths reported"),
    (100, 8.0, "More than one hundred deaths reported"),
    (50, 7.0, "Dozens of deaths reported"),
    (10, 6.0, "At least ten deaths reported"),
    (1, 4.5, "Deaths reported"),
)

MAGNITUDE_SEVERITY = (
    (8.0, 9.5),
    (7.0, 8.5),
    (6.0, 7.0),
    (5.0, 5.0),
    (4.0, 3.5),
    (0.0, 2.0),
)


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def severity_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    for threshold, label in LABELS:
        if score >= threshold:
            return label
    return "minimal"


def _casualty_band(value: int) -> tuple[float, str] | None:
    for threshold, score, note in CASUALTY_BANDS:
        if value >= threshold:
            return score, note
    return None


def _magnitude_band(magnitude: float) -> tuple[float, str]:
    for threshold, score in MAGNITUDE_SEVERITY:
        if magnitude >= threshold:
            return score, f"Magnitude {magnitude:.1f} (USGS scale)"
    return 2.0, f"Magnitude {magnitude:.1f}"


def assess_severity(
    *,
    category: str | None,
    subcategory: str | None,
    reported_casualties: int | None = None,
    magnitude: float | None = None,
    official_severity: str | None = None,
    country_count: int | None = None,
    location_precision: str | None = None,
    article_count: int = 1,
    provider_severity: float | None = None,
) -> dict:
    components: list[dict] = []
    missing: list[str] = []

    # 1. Category baseline -------------------------------------------------
    baseline = CATEGORY_BASELINES.get(category or "other", 2.0)
    baseline += SUBCATEGORY_MODIFIERS.get(subcategory or "", 0.0)
    components.append(
        {
            "factor": "event_type",
            "value": round(_clamp(baseline), 2),
            "weight": 0.30,
            "evidence": f"Category `{category or 'other'}` / subtype `{subcategory or 'unclassified'}`",
            "confidence": 0.6,
        }
    )

    # 2. Human impact ------------------------------------------------------
    if reported_casualties:
        band = _casualty_band(int(reported_casualties))
        if band:
            components.append(
                {
                    "factor": "human_impact",
                    "value": band[0],
                    "weight": 0.35,
                    "evidence": band[1],
                    "confidence": 0.8,
                }
            )
    else:
        missing.append("human_impact")

    # 3. Physical scale (earthquake magnitude, when structured) -----------
    if magnitude is not None:
        value, evidence = _magnitude_band(float(magnitude))
        components.append(
            {
                "factor": "physical_magnitude",
                "value": value,
                "weight": 0.40,
                "evidence": evidence,
                "confidence": 0.95,
            }
        )

    # 4. Official severity (CAP urgency/severity, meteorological warnings) --
    if official_severity:
        mapping = {
            "extreme": 9.5, "severe": 8.0, "moderate": 5.0, "minor": 3.0,
            "unknown": None, "red": 9.0, "orange": 7.0, "yellow": 5.0,
        }
        mapped = mapping.get(str(official_severity).strip().lower())
        if mapped is not None:
            components.append(
                {
                    "factor": "official_severity",
                    "value": mapped,
                    "weight": 0.30,
                    "evidence": f"Official severity level `{official_severity}`",
                    "confidence": 0.95,
                }
            )

    # 5. Geographic scale --------------------------------------------------
    if country_count is not None and country_count > 0:
        geo = min(10.0, 3.0 + (1.5 * (country_count - 1)))
        components.append(
            {
                "factor": "geographic_scale",
                "value": round(geo, 2),
                "weight": 0.10,
                "evidence": f"{country_count} country/countries referenced",
                "confidence": 0.5,
            }
        )
    else:
        missing.append("geographic_scale")

    # 6. First-party provider severity (e.g. computed from a USGS magnitude)
    #    -- used only when no richer structured attribute exists.
    if provider_severity is not None and magnitude is None and not official_severity:
        components.append(
            {
                "factor": "provider_severity",
                "value": round(_clamp(float(provider_severity)), 2),
                "weight": 0.30,
                "evidence": "Severity derived by the structured data provider.",
                "confidence": 0.9,
            }
        )

    # Weighted mean over available components (weights renormalised).
    total_weight = sum(c["weight"] for c in components)
    if total_weight <= 0:
        return {
            "score": None,
            "label": "unknown",
            "components": components,
            "missing_evidence": missing,
            "methodology": "No severity evidence available.",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    score = sum(c["value"] * c["weight"] for c in components) / total_weight

    # Location imprecision caps how confidently we can rate local impact.
    if (location_precision or "unknown") in {"country", "unknown", "approximate"}:
        score -= 0.3

    score = round(_clamp(score), 2)

    return {
        "score": score,
        "label": severity_label(score),
        "components": [
            {**c, "contribution": round(c["value"] * c["weight"] / total_weight, 3)}
            for c in components
        ],
        "missing_evidence": missing,
        "methodology": (
            "Weighted mean of evidence-backed factors (event type, human impact, "
            "physical magnitude, official severity level, geographic scale). "
            "Missing factors are excluded rather than defaulted; the score is "
            "reduced when location precision cannot support a local impact claim."
        ),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
