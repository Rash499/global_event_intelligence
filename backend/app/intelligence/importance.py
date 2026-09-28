def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def score_event_importance(data):
    severity = clamp(float(data.get("severity", 5) or 5), 0.0, 10.0)
    geographic_impact = clamp(float(data.get("geographic_impact", 3) or 3), 0.0, 10.0)
    source_coverage = clamp(float(data.get("source_coverage", 2) or 2), 0.0, 10.0)
    human_impact = clamp(float(data.get("human_impact", 3) or 3), 0.0, 10.0)
    economic_impact = clamp(float(data.get("economic_impact", 2) or 2), 0.0, 10.0)
    urgency = clamp(float(data.get("urgency", 3) or 3), 0.0, 10.0)

    weighted = (
        severity * 0.25
        + geographic_impact * 0.15
        + source_coverage * 0.15
        + human_impact * 0.20
        + economic_impact * 0.10
        + urgency * 0.15
    )

    total = clamp(round(weighted), 1, 10)
    return int(total)
