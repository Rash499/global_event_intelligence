"""Deterministic event intelligence utilities for clustering, scoring, and verification."""

from .classification import classify_article, normalize_category
from .clustering import find_matching_event, score_event_similarity
from .confidence import score_event_confidence
from .deduplication import is_duplicate, normalize_title
from .importance import score_event_importance
from .verification import determine_corroboration_level

__all__ = [
    "classify_article",
    "normalize_category",
    "find_matching_event",
    "score_event_similarity",
    "score_event_confidence",
    "is_duplicate",
    "normalize_title",
    "score_event_importance",
    "determine_corroboration_level",
]
