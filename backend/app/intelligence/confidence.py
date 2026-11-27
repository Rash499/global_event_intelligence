"""Intelligence confidence: *how reliable is the available information?*

This replaces the old scoring, which:

* counted every article link as a source (``source_count``) and therefore
  rewarded syndication;
* defaulted unknown inputs to 0.5 so every event looked equally certain;
* produced a single opaque number.

The new score separates what is measurable and caches nothing that is not
evidence-backed. Unknown inputs are excluded, not defaulted (unknown != 0.5).
"""

from __future__ import annotations

from datetime import datetime, timezone

COMPONENT_WEIGHTS = {
    "independent_corroboration": 0.34,
    "source_diversity": 0.12,
    "reporting_directness": 0.10,
    "time_precision": 0.10,
    "location_precision": 0.12,
    "classification_certainty": 0.12,
    "official_confirmation": 0.10,
}

LOCATION_PRECISION_SCORE = {
    "exact": 1.0,
    "city": 0.85,
    "admin_region": 0.7,
    "country": 0.45,
    "approximate": 0.3,
    "unknown": 0.15,
}

TIME_PRECISION_SCORE = {
    "timestamp": 1.0,
    "date": 0.75,
    "approximate": 0.55,
    "unknown": 0.2,
}


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def corroboration_component(independent_publishers: int) -> tuple[float, str]:
    """Saturating curve over *independent* publishers.

    One publisher is weak evidence. Two independent newsrooms is meaningfully
    stronger. Beyond four, additional publishers add little: the information is
    already widely established.
    """
    count = max(0, independent_publishers)
    if count <= 0:
        return 0.0, "No independent publisher identified."
    table = {1: 0.45, 2: 0.72, 3: 0.85, 4: 0.92}
    value = table.get(count, 0.95)
    return value, f"{count} independent publisher(s) corroborate this event."


def confidence_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "moderate"
    if score >= 0.45:
        return "limited"
    return "low"


LEGACY_COMPONENT_MAP = {
    "location_confidence": "location_precision",
    "time_confidence": "time_precision",
    "classification_confidence": "classification_confidence",
    "article_similarity": "source_diversity",
}


def score_event_confidence(data: dict) -> float:
    """Backwards-compatible numeric helper.

    It accepts the legacy ``source_count``/``article_count``/``*_confidence``
    keyword names (which callers and older tests still pass) and maps them onto
    the evidence-based inputs. ``source_count`` is interpreted as the number of
    *independent publishers*, which is what the old code was trying to measure.
    """
    score = data.get("confidence")
    if isinstance(score, (int, float)) and "source_count" not in data:
        return clamp(float(score))

    independent = data.get("independent_publishers")
    if independent is None and data.get("source_count") is not None:
        independent = data.get("source_count")

    location_precision = data.get("location_precision")
    if location_precision is None and data.get("location_confidence") is not None:
        value = float(data["location_confidence"])
        location_precision = (
            "exact" if value >= 0.9 else "city" if value >= 0.75
            else "admin_region" if value >= 0.6 else "country" if value >= 0.4 else "unknown"
        )

    time_precision = data.get("time_precision")
    if time_precision is None and data.get("time_confidence") is not None:
        value = float(data["time_confidence"])
        time_precision = "timestamp" if value >= 0.8 else "date" if value >= 0.6 else "approximate"

    similarity = data.get("source_diversity")
    return assess_confidence(
        independent_publishers=independent,
        total_articles=int(data.get("article_count") or 0) or None,
        location_precision=location_precision,
        time_precision=time_precision,
        classification_confidence=data.get("classification_confidence"),
        syndicated_publishers=0,
        reporting_types=["direct"] if similarity is None else None,
        direct_articles=int(round(float(similarity) * max(int(data.get("article_count") or 1), 1)))
        if similarity is not None
        else None,
    )["score"] or 0.0


def assess_confidence(
    *,
    independent_publishers: int | None = None,
    syndicated_publishers: int = 0,
    total_articles: int = 0,
    direct_articles: int | None = None,
    reporting_types: list[str] | None = None,
    location_precision: str | None = None,
    time_precision: str | None = None,
    classification_confidence: float | None = None,
    official_sources: int = 0,
    contradictions: int = 0,
) -> dict:
    components: list[dict] = []
    missing: list[str] = []

    if independent_publishers is not None:
        value, evidence = corroboration_component(independent_publishers)
        components.append(
            {
                "factor": "independent_corroboration",
                "value": round(value, 3),
                "weight": COMPONENT_WEIGHTS["independent_corroboration"],
                "evidence": evidence,
                "confidence": 0.9,
            }
        )
    else:
        missing.append("independent_corroboration")

    if total_articles:
        distinct = (independent_publishers or 0) + syndicated_publishers
        diversity = clamp(distinct / max(total_articles, 1))
        components.append(
            {
                "factor": "source_diversity",
                "value": round(diversity, 3),
                "weight": COMPONENT_WEIGHTS["source_diversity"],
                "evidence": (
                    f"{independent_publishers or 0} independent and "
                    f"{syndicated_publishers} syndicated publisher(s) across "
                    f"{total_articles} article(s)."
                ),
                "confidence": 0.8,
            }
        )
    else:
        missing.append("source_diversity")

    types = reporting_types or []
    if types:
        direct = direct_articles if direct_articles is not None else types.count("direct")
        directness = clamp(direct / max(len(types), 1))
        components.append(
            {
                "factor": "reporting_directness",
                "value": round(directness, 3),
                "weight": COMPONENT_WEIGHTS["reporting_directness"],
                "evidence": f"{direct} of {len(types)} article(s) are direct reporting.",
                "confidence": 0.7,
            }
        )
    else:
        missing.append("reporting_directness")

    if location_precision:
        value = LOCATION_PRECISION_SCORE.get(location_precision, 0.15)
        components.append(
            {
                "factor": "location_precision",
                "value": value,
                "weight": COMPONENT_WEIGHTS["location_precision"],
                "evidence": f"Location established at `{location_precision}` precision.",
                "confidence": 0.85,
            }
        )
    else:
        missing.append("location_precision")

    if time_precision:
        value = TIME_PRECISION_SCORE.get(time_precision, 0.2)
        components.append(
            {
                "factor": "time_precision",
                "value": value,
                "weight": COMPONENT_WEIGHTS["time_precision"],
                "evidence": f"Incident time known to `{time_precision}` precision.",
                "confidence": 0.85,
            }
        )
    else:
        missing.append("time_precision")

    if classification_confidence is not None:
        components.append(
            {
                "factor": "classification_certainty",
                "value": round(clamp(classification_confidence), 3),
                "weight": COMPONENT_WEIGHTS["classification_certainty"],
                "evidence": "Deterministic/AI taxonomy classification confidence.",
                "confidence": 0.7,
            }
        )
    else:
        missing.append("classification_certainty")

    if official_sources:
        value = clamp(0.6 + 0.15 * official_sources)
        components.append(
            {
                "factor": "official_confirmation",
                "value": round(value, 3),
                "weight": COMPONENT_WEIGHTS["official_confirmation"],
                "evidence": f"{official_sources} official source(s) referenced.",
                "confidence": 0.9,
            }
        )

    if not components:
        return {
            "score": None,
            "label": "unknown",
            "components": [],
            "missing_evidence": missing,
            "penalties": [],
            "methodology": "No corroborating evidence available.",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    total_weight = sum(c["weight"] for c in components)
    score = sum(c["value"] * c["weight"] for c in components) / total_weight

    penalties: list[dict] = []
    if contradictions:
        penalty = min(0.25, 0.08 * contradictions)
        score -= penalty
        penalties.append(
            {
                "reason": "contradictory_reporting",
                "penalty": round(penalty, 3),
                "detail": f"{contradictions} contradictory report(s) detected.",
            }
        )

    score = round(clamp(score), 3)

    return {
        "score": score,
        "label": confidence_label(score),
        "components": [
            {**c, "contribution": round(c["value"] * c["weight"] / total_weight, 3)}
            for c in components
        ],
        "missing_evidence": missing,
        "penalties": penalties,
        "methodology": (
            "Weighted mean of independent corroboration, source diversity, reporting "
            "directness, location and time precision, classification certainty and "
            "official confirmation. Syndicated copies are excluded from "
            "corroboration; contradictory reporting applies a penalty."
        ),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
