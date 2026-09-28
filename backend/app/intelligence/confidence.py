def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def score_event_confidence(data):
    source_count = max(1, int(data.get("source_count") or 1))
    article_count = max(1, int(data.get("article_count") or 1))
    classification_confidence = clamp(float(data.get("classification_confidence", 0.5) or 0.5), 0.0, 1.0)
    location_confidence = clamp(float(data.get("location_confidence", 0.5) or 0.5), 0.0, 1.0)
    time_confidence = clamp(float(data.get("time_confidence", 0.5) or 0.5), 0.0, 1.0)
    article_similarity = clamp(float(data.get("article_similarity", 0.6) or 0.6), 0.0, 1.0)

    source_component = min(0.35, (source_count - 1) * 0.06)
    article_component = min(0.15, (article_count - 1) * 0.02)

    score = (
        0.25 * classification_confidence
        + 0.20 * location_confidence
        + 0.15 * time_confidence
        + 0.20 * article_similarity
        + source_component
        + article_component
    )

    score = clamp(round(score, 2), 0.0, 1.0)
    return score
