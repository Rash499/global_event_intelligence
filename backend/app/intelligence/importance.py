"""Backwards-compatible importance wrapper.

``importance`` is the integer 1-10 column the original API exposes. It is now
derived from the evidence-based severity assessment instead of synthetic inputs,
so ``importance`` and ``severity`` cannot disagree.
"""

from __future__ import annotations


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def importance_from_severity(severity: float | None, fallback: int = 5) -> int:
    if severity is None:
        return int(clamp(fallback, 1, 10))
    return int(clamp(round(float(severity)), 1, 10))


def score_event_importance(data: dict) -> int:
    """Legacy signature: averages whatever evidence-backed factors are present."""
    severity = data.get("severity")
    if severity is not None:
        return importance_from_severity(float(severity))
    numeric = [
        float(data[key])
        for key in ("human_impact", "physical_magnitude", "official_severity")
        if isinstance(data.get(key), (int, float))
    ]
    if not numeric:
        return importance_from_severity(None)
    return importance_from_severity(sum(numeric) / len(numeric))
