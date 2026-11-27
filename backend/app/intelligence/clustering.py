"""Multi-signal event matching, relationship typing and lifecycle.

The original matcher scored title token overlap (0.40), same country (0.20),
same category (0.15), distance (0.15) and time proximity (0.15) and merged at
0.70.  Because country + category + time alone reach 0.50, unrelated incidents
in the same country could merge on a weak headline overlap.

This version:

* weights *discriminative* signals (shared location, shared distinctive terms)
  above incidental ones (same country, same category);
* requires at least one substantive corroborating signal before merging;
* separates "same event" from "related event" instead of collapsing both;
* exposes the decision and its evidence so the pipeline can store a
  relationship with a confidence and a reason.

Embeddings are **not** required. When the RAG embedding provider is available a
semantic similarity signal can be supplied by the caller; otherwise the
lexical signals below are used unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from .deduplication import STOPWORDS, normalize_title
from .normalize_time import parse_timestamp

EVENT_CLUSTER_TIME_WINDOW_HOURS = 48
EVENT_CLUSTER_SIMILARITY_THRESHOLD = 0.62
EVENT_CLUSTER_DISTANCE_KM = 200
RELATED_TIME_WINDOW_HOURS = 24 * 14
RELATED_DISTANCE_KM = 400

SAME_EVENT = "same_event"
RELATED_EVENT = "related_event"
SIMILAR_EVENT = "similar_event"
INDEPENDENT_EVENT = "independent_event"


def haversine_distance_km(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = radians(float(lat1)), radians(float(lat2))
    dphi = radians(float(lat2) - float(lat1))
    dlambda = radians(float(lon2) - float(lon1))
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(max(0.0, min(1.0, a))))


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_CAPITALISED_RE = re.compile(r"\b([A-Z][a-zA-Z]{2,})\b")


def _non_discriminative_terms() -> set[str]:
    """Vocabulary that names *what kind* of event it is, not *which* one.

    "airstrike" and "Ukraine" appear in every Ukraine airstrike report, so they
    cannot serve as anchors without merging unrelated incidents.
    """
    global _NON_DISCRIMINATIVE
    if _NON_DISCRIMINATIVE is None:
        from .taxonomy import TAXONOMY
        from .geolocation import COUNTRY_BY_NAME, NAME_ALIASES

        terms: set[str] = set()
        for entry in TAXONOMY.values():
            terms.update(word.lower() for word in entry["keywords"])
            for sub in entry["subcategories"].values():
                terms.update(word.lower() for word in sub["keywords"])
        terms.update(COUNTRY_BY_NAME.keys())
        terms.update(NAME_ALIASES.keys())
        # Split multi-word terms so individual words are excluded too.
        expanded = set()
        for term in terms:
            expanded.add(term)
            expanded.update(term.split())
        _NON_DISCRIMINATIVE = expanded
    return _NON_DISCRIMINATIVE


_NON_DISCRIMINATIVE: set[str] | None = None


def _anchors(item: dict) -> set[str]:
    """Proper nouns and figures that identify *which* incident is described."""
    text = f"{item.get('title') or item.get('event_title') or ''}"
    excluded = _non_discriminative_terms()
    anchors = {match.lower() for match in _NUMBER_RE.findall(text)}
    for word in _CAPITALISED_RE.findall(text):
        lowered = word.lower()
        if lowered in STOPWORDS or lowered in excluded or len(lowered) <= 2:
            continue
        anchors.add(lowered)
    return anchors


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in value.split()
        if len(token) > 2 and token not in STOPWORDS and not token.isdigit()
    }


@dataclass
class MatchResult:
    score: float
    decision: str
    signals: list[dict]
    reason: str

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "decision": self.decision,
            "signals": self.signals,
            "reason": self.reason,
        }


def _time_delta_hours(left, right) -> float | None:
    left_time = parse_timestamp(left.get("event_time") or left.get("published_at"))
    right_time = parse_timestamp(right.get("event_time") or right.get("published_at"))
    if not left_time or not right_time:
        return None
    return abs((left_time - right_time).total_seconds()) / 3600


def compare_events(left: dict, right: dict, semantic_similarity: float | None = None) -> MatchResult:
    """Compare a candidate article/event against a stored event."""
    signals: list[dict] = []
    score = 0.0

    left_title = normalize_title(left.get("title") or left.get("event_title") or "")
    right_title = normalize_title(right.get("title") or right.get("event_title") or "")
    left_tokens, right_tokens = _tokens(left_title), _tokens(right_title)
    shared = left_tokens & right_tokens

    if left_title and right_title:
        if left_title == right_title:
            score += 0.45
            signals.append({"signal": "title", "value": 1.0, "detail": "Identical normalised headline"})
        elif len(shared) >= 2:
            jaccard = len(shared) / max(len(left_tokens | right_tokens), 1)
            containment = len(shared) / min(len(left_tokens), len(right_tokens))
            contribution = min(0.42, (jaccard * 0.30) + (containment * 0.28))
            score += contribution
            signals.append(
                {
                    "signal": "title",
                    "value": round(max(jaccard, containment), 3),
                    "detail": f"Shared distinctive terms: {', '.join(sorted(shared)[:6])}",
                }
            )

    # Anchors are the strongest lexical evidence: a shared proper noun or a
    # shared figure ("magnitude 6.8", "Japan") ties two reports to one incident.
    left_anchors = _anchors(left)
    right_anchors = _anchors(right)
    shared_anchors = left_anchors & right_anchors
    if shared_anchors and left_tokens and right_tokens:
        containment = len(shared) / max(min(len(left_tokens), len(right_tokens)), 1)
        if containment >= 0.30:
            score += 0.25
            signals.append(
                {
                    "signal": "shared_anchors",
                    "value": round(min(1.0, len(shared_anchors) / 2), 3),
                    "detail": f"Shared named entities/figures: {', '.join(sorted(shared_anchors)[:6])}",
                }
            )

    # Geographic agreement: precise coordinates are strong, country is weak.
    left_lat, left_lon = _parse_float(left.get("latitude")), _parse_float(left.get("longitude"))
    right_lat, right_lon = _parse_float(right.get("latitude")), _parse_float(right.get("longitude"))
    left_precision = left.get("location_precision") or "unknown"
    right_precision = right.get("location_precision") or "unknown"

    geo_discriminating = False
    if left_lat is not None and right_lat is not None:
        distance = haversine_distance_km(left_lat, left_lon, right_lat, right_lon)
        precise = left_precision in {"exact", "city"} and right_precision in {"exact", "city"}
        if distance <= EVENT_CLUSTER_DISTANCE_KM:
            bonus = 0.30 if precise else 0.14
            score += bonus
            geo_discriminating = precise
            signals.append(
                {
                    "signal": "proximity",
                    "value": round(1 - min(1.0, distance / max(EVENT_CLUSTER_DISTANCE_KM, 1)), 3),
                    "detail": f"{distance:.0f} km apart ({left_precision}/{right_precision} precision)",
                }
            )

    left_country = (left.get("country_code") or "").upper()
    right_country = (right.get("country_code") or "").upper()
    same_country = bool(left_country and left_country == right_country)
    if same_country:
        # Deliberately small: sharing a country is not evidence of the same event.
        score += 0.08
        signals.append(
            {"signal": "country", "value": 1.0, "detail": f"Both events reference {left_country}"}
        )

    left_category = (left.get("category") or "").lower()
    right_category = (right.get("category") or "").lower()
    same_category = bool(left_category and left_category == right_category)
    same_subcategory = bool(
        left.get("subcategory")
        and left.get("subcategory") == right.get("subcategory")
    )
    if same_category:
        score += 0.06
        signals.append({"signal": "category", "value": 1.0, "detail": f"Both classified as {left_category}"})
    if same_subcategory:
        score += 0.08
        signals.append(
            {"signal": "subcategory", "value": 1.0, "detail": f"Same subtype {left.get('subcategory')}"}
        )

    delta = _time_delta_hours(left, right)
    time_close = delta is not None and delta <= EVENT_CLUSTER_TIME_WINDOW_HOURS
    if time_close:
        score += 0.10
        signals.append(
            {"signal": "time", "value": round(1 - min(1.0, delta / EVENT_CLUSTER_TIME_WINDOW_HOURS), 3),
             "detail": f"Reports {delta:.1f}h apart"}
        )

    if semantic_similarity is not None:
        contribution = max(0.0, min(0.35, float(semantic_similarity) * 0.35))
        score += contribution
        signals.append(
            {"signal": "semantic", "value": round(float(semantic_similarity), 3), "detail": "Embedding similarity"}
        )

    score = min(1.0, max(0.0, score))

    # A merge needs substance: shared *anchors* (a named entity or figure that
    # identifies the incident), precise co-location, high semantic similarity, or
    # a very strong headline match. Country + category + time is never enough.
    substantive = (
        bool(shared_anchors)
        or geo_discriminating
        or (semantic_similarity is not None and semantic_similarity >= 0.72)
        or (
            left_tokens
            and right_tokens
            and len(shared) / max(min(len(left_tokens), len(right_tokens)), 1) >= 0.75
        )
    )

    if score >= EVENT_CLUSTER_SIMILARITY_THRESHOLD and substantive:
        decision = SAME_EVENT
        reason = "Headline terms and location/time evidence agree."
    elif (
        same_country
        and (same_category or same_subcategory)
        and delta is not None
        and delta <= RELATED_TIME_WINDOW_HOURS
    ):
        decision = RELATED_EVENT
        reason = "Same country and theme within the related-event window, but the reports describe different incidents."
    elif same_category and len(shared) >= 1:
        decision = SIMILAR_EVENT
        reason = "Similar theme and wording but insufficient evidence of the same incident."
    else:
        decision = INDEPENDENT_EVENT
        reason = "No shared evidence beyond incidental metadata."

    return MatchResult(score=score, decision=decision, signals=signals, reason=reason)


def score_event_similarity(left: dict, right: dict) -> float:
    """Backwards-compatible numeric similarity (used by existing callers)."""
    return compare_events(left, right).score


def find_matching_event(article: dict, existing_events: list[dict]) -> dict | None:
    """Return the stored event that the article describes, if any."""
    best_event, best_score = None, 0.0
    for event in existing_events:
        result = compare_events(article, event)
        if result.decision == SAME_EVENT and result.score > best_score:
            best_event, best_score = event, result.score
    return best_event


def find_related_events(article: dict, existing_events: list[dict], limit: int = 5) -> list[dict]:
    """Events that are connected but must not be merged."""
    related = []
    for event in existing_events:
        if str(event.get("id")) == str(article.get("event_id")):
            continue
        result = compare_events(article, event)
        if result.decision in {RELATED_EVENT, SIMILAR_EVENT}:
            related.append(
                {
                    "event_id": event.get("id"),
                    "decision": result.decision,
                    "relationship": "related_to" if result.decision == RELATED_EVENT else "similar_to",
                    "confidence": round(result.score, 3),
                    "reason": result.reason,
                    "signals": result.signals,
                }
            )
    related.sort(key=lambda item: -item["confidence"])
    return related[:limit]


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------
LIFECYCLE_STATES = (
    "newly_detected", "developing", "ongoing", "escalating",
    "de_escalating", "resolved", "archived", "uncertain",
)


def derive_event_state(
    *,
    created_at: str | None,
    last_seen_at: str | None,
    current_state: str | None = None,
    report_count: int = 0,
    independent_publishers: int = 0,
    recent_report_count: int = 0,
    previous_report_count: int = 0,
    resolution_evidence: bool = False,
    now=None,
) -> tuple[str, str]:
    """Return ``(state, explanation)``.

    An event is never marked resolved just because reports stopped arriving:
    resolution requires explicit evidence (an official all-clear, a ceasefire,
    a recovery announcement) or a long, quiet period combined with a low
    severity classification. Otherwise the event stays ``ongoing``/``developing``
    and is eventually ``archived`` by age.
    """
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    last = parse_timestamp(last_seen_at) or parse_timestamp(created_at)
    first = parse_timestamp(created_at)

    if resolution_evidence:
        return "resolved", "Resolution evidence present in the reporting."

    age_hours = (now - first).total_seconds() / 3600 if first else 0.0
    quiet_hours = (now - last).total_seconds() / 3600 if last else 0.0

    if quiet_hours > 24 * 30:
        return "archived", "No reporting for more than 30 days; event archived for reference."

    if report_count <= 1 and age_hours < 12:
        return "newly_detected", "A single initial report has been recorded."

    if previous_report_count and recent_report_count > previous_report_count * 1.5 and recent_report_count >= 3:
        return "escalating", "Reporting volume increased by more than 50% in the latest window."

    if previous_report_count and recent_report_count < previous_report_count * 0.5 and quiet_hours < 48:
        return "de_escalating", "Reporting volume halved in the latest window."

    if independent_publishers >= 2 and report_count >= 3 and quiet_hours < 6:
        return "developing", "Multiple independent publishers are actively reporting new details."

    if quiet_hours > 24 * 7:
        return "uncertain", "No new reporting for over a week; the situation cannot be confirmed."

    if current_state in {"escalating", "de_escalating"} and quiet_hours < 12:
        return current_state, "Retaining the state established by the latest reporting trend."

    return "ongoing", "Reporting continues without a decisive change in tempo."
