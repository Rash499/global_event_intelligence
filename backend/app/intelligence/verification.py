"""Corroboration vocabulary.

Kept for backwards compatibility, but it now maps *independent publisher* counts
(not raw article links) onto the labels the UI and the assistant display.
"""

CORROBORATION_LEVELS = (
    (4, "strong"),
    (2, "corroborated"),
    (1, "single"),
    (0, "insufficient_evidence"),
)


def determine_corroboration_level(independent_publishers) -> str:
    count = max(0, int(independent_publishers or 0))
    for threshold, label in CORROBORATION_LEVELS:
        if count >= threshold:
            return label
    return "insufficient_evidence"


def corroboration_description(level: str) -> str:
    return {
        "strong": "Four or more independent publishers report this event.",
        "corroborated": "Two or three independent publishers report this event.",
        "single": "Reported by a single independent publisher.",
        "insufficient_evidence": "No independent publisher could be identified.",
    }.get(level, "Corroboration level unknown.")
