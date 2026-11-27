"""Classification, geolocation, severity, confidence, priority, clustering, lifecycle."""

from __future__ import annotations

import pytest

from app.intelligence.assessment import build_event_assessment
from app.intelligence.classification import (
    classify_article,
    merge_ai_classification,
    normalize_category,
)
from app.intelligence.clustering import (
    EVENT_CLUSTER_SIMILARITY_THRESHOLD,
    INDEPENDENT_EVENT,
    RELATED_EVENT,
    SAME_EVENT,
    compare_events,
    derive_event_state,
)
from app.intelligence.confidence import assess_confidence
from app.intelligence.deduplication import IndependenceAssessment
from app.intelligence.geolocation import extract_location
from app.intelligence.priority import assess_priority
from app.intelligence.severity import assess_severity
from app.intelligence.taxonomy import TAXONOMY, TAXONOMY_VERSION, taxonomy_payload


# ----------------------------------------------------------------------
# Taxonomy and classification
# ----------------------------------------------------------------------
def test_taxonomy_has_all_required_categories():
    payload = taxonomy_payload()
    assert payload["version"] == TAXONOMY_VERSION
    keys = {category["key"] for category in payload["categories"]}
    for expected in (
        "armed_conflict", "political_development", "protest_unrest",
        "terrorism_extremism", "natural_disaster", "severe_weather",
        "public_health", "humanitarian", "economic_financial",
        "energy_infrastructure", "transportation", "cyber_technology",
        "crime_public_safety", "international_relations", "environmental", "other",
    ):
        assert expected in keys
    for category in payload["categories"]:
        assert category["subcategories"], f"{category['key']} has no subcategories"


def test_natural_disaster_subcategories_exist():
    subs = {s["key"] for s in TAXONOMY["natural_disaster"]["subcategories"].values()}
    assert {"earthquake", "flood", "tropical_cyclone", "landslide", "wildfire", "volcanic_activity", "tsunami"} <= subs


@pytest.mark.parametrize(
    "title,expected_category,expected_sub",
    [
        ("Magnitude 7.1 earthquake strikes Japan", "natural_disaster", "earthquake"),
        ("Rival factions clash in Sudan, dozens killed", "armed_conflict", "armed_clash"),
        ("Protests erupt in Nairobi over fuel prices", "protest_unrest", "demonstration"),
        ("Ransomware attack on hospital network", "cyber_technology", "cyber_attack"),
        ("Cholera outbreak spreads in Yemen", "public_health", "disease_outbreak"),
        ("President announces election date", "political_development", "election"),
        ("Central bank raises interest rates", "economic_financial", "economic_policy"),
        ("Power outage leaves city without electricity", "energy_infrastructure", "power_disruption"),
    ],
)
def test_deterministic_classification(title, expected_category, expected_sub):
    result = classify_article({"title": title})
    assert result["category"] == expected_category
    assert result["subcategory"] == expected_sub
    assert result["confidence"] > 0.5
    assert result["method"] == "deterministic"


def test_unclassifiable_text_falls_back_to_other():
    result = classify_article({"title": "A quiet afternoon in the park"})
    assert result["category"] == "other"
    assert result["needs_review"] is True


def test_partial_word_matches_do_not_classify():
    """"port" inside "reported" must not make an event a maritime incident."""
    result = classify_article({"title": "Fighting reported across the region"})
    assert result["category"] != "transportation"


def test_legacy_category_labels_are_mapped():
    assert normalize_category("natural_disaster") == "natural_disaster"
    assert normalize_category("conflict") == "armed_conflict"
    assert normalize_category("Politics") == "political_development"
    assert normalize_category("health") == "public_health"
    assert normalize_category("nonsense") == "other"


def test_ai_merge_cannot_produce_unknown_categories():
    deterministic = classify_article({"title": "Magnitude 6.0 earthquake"})
    merged = merge_ai_classification(deterministic, "interdimensional_weather", 0.95)
    assert merged["category"] in TAXONOMY
    assert merged["method"] == "ai_assisted"


# ----------------------------------------------------------------------
# Geolocation
# ----------------------------------------------------------------------
def test_country_only_location_has_no_coordinates():
    result = extract_location("An earthquake struck Japan today")
    assert result.country_code == "JP"
    assert result.precision == "country"
    assert result.latitude is None and result.longitude is None


def test_city_location_has_city_precision():
    result = extract_location("Flooding in Colombo displaced thousands")
    assert result.precision == "city"
    assert result.country_code == "LK"
    assert result.latitude == pytest.approx(6.9271)


def test_approximate_context_lowers_precision():
    result = extract_location("Fighting near Khartoum intensified")
    assert result.precision == "approximate"
    assert result.confidence < 0.85


def test_unknown_location_is_reported_as_unknown():
    result = extract_location("A statement was released")
    assert result.precision == "unknown"
    assert result.latitude is None


# ----------------------------------------------------------------------
# Severity
# ----------------------------------------------------------------------
def test_severity_is_evidence_based_and_explainable():
    severity = assess_severity(
        category="natural_disaster",
        subcategory="earthquake",
        magnitude=7.2,
        reported_casualties=12,
        country_count=1,
        location_precision="exact",
    )
    assert severity["score"] is not None
    assert severity["label"] in {"moderate", "high", "critical"}
    assert severity["components"]
    assert severity["methodology"]
    names = {component["factor"] for component in severity["components"]}
    assert "physical_magnitude" in names
    assert "human_impact" in names


def test_missing_evidence_is_declared_not_defaulted():
    severity = assess_severity(category="other", subcategory="unclassified")
    assert "human_impact" in severity["missing_evidence"]
    assert all(component["factor"] != "human_impact" for component in severity["components"])


def test_larger_earthquake_is_more_severe():
    small = assess_severity(category="natural_disaster", subcategory="earthquake", magnitude=3.0)
    large = assess_severity(category="natural_disaster", subcategory="earthquake", magnitude=8.0)
    assert large["score"] > small["score"]


def test_more_casualties_increase_severity():
    few = assess_severity(category="armed_conflict", subcategory="armed_clash", reported_casualties=2)
    many = assess_severity(category="armed_conflict", subcategory="armed_clash", reported_casualties=800)
    assert many["score"] > few["score"]


# ----------------------------------------------------------------------
# Confidence
# ----------------------------------------------------------------------
def test_syndicated_publishers_do_not_raise_confidence():
    weak = assess_confidence(
        independent_publishers=1, syndicated_publishers=6, total_articles=7,
        reporting_types=["direct"] * 7, location_precision="city",
        time_precision="timestamp", classification_confidence=0.8,
    )
    strong = assess_confidence(
        independent_publishers=3, syndicated_publishers=0, total_articles=3,
        reporting_types=["direct"] * 3, location_precision="city",
        time_precision="timestamp", classification_confidence=0.8,
    )
    assert strong["score"] > weak["score"]


def test_confidence_improves_with_independent_publishers():
    one = assess_confidence(independent_publishers=1, total_articles=1, reporting_types=["direct"],
                            location_precision="country", time_precision="timestamp")
    three = assess_confidence(independent_publishers=3, total_articles=3, reporting_types=["direct"] * 3,
                              location_precision="country", time_precision="timestamp")
    assert three["score"] > one["score"]


def test_contradictions_lower_confidence_and_are_reported():
    clean = assess_confidence(independent_publishers=2, total_articles=2,
                              reporting_types=["direct"] * 2,
                              location_precision="city", time_precision="timestamp")
    conflicted = assess_confidence(independent_publishers=2, total_articles=2,
                                   reporting_types=["direct"] * 2,
                                   location_precision="city", time_precision="timestamp",
                                   contradictions=2)
    assert conflicted["score"] < clean["score"]
    assert conflicted["penalties"]


def test_unknown_confidence_is_none_not_a_default_number():
    result = assess_confidence()
    assert result["score"] is None
    assert result["label"] == "unknown"


# ----------------------------------------------------------------------
# Priority
# ----------------------------------------------------------------------
def test_priority_combines_severity_confidence_and_recency():
    from datetime import datetime, timezone

    fresh = datetime.now(timezone.utc).isoformat()
    high = assess_priority(severity=9.0, confidence=0.9, occurred_at=fresh)
    low = assess_priority(severity=2.0, confidence=0.5, occurred_at="2020-01-01T00:00:00Z")
    assert high["score"] > low["score"]
    assert high["label"] in {"immediate", "elevated"}
    assert high["components"]


def test_escalation_increases_priority():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    stable = assess_priority(severity=6.0, confidence=0.7, occurred_at=now, escalation_trend="stable")
    escalating = assess_priority(severity=6.0, confidence=0.7, occurred_at=now, escalation_trend="escalating")
    assert escalating["score"] > stable["score"]


# ----------------------------------------------------------------------
# Clustering
# ----------------------------------------------------------------------
def test_same_event_reports_are_merged():
    left = {
        "title": "Magnitude 6.8 earthquake strikes central Japan",
        "country_code": "JP", "category": "natural_disaster", "subcategory": "earthquake",
        "event_time": "2026-11-27T04:00:00Z",
    }
    right = {
        "title": "Japan earthquake: magnitude 6.8 quake hits central region",
        "country_code": "JP", "category": "natural_disaster", "subcategory": "earthquake",
        "event_time": "2026-11-27T05:00:00Z",
    }
    result = compare_events(left, right)
    assert result.decision == SAME_EVENT
    assert result.score >= EVENT_CLUSTER_SIMILARITY_THRESHOLD
    assert result.signals


def test_same_country_and_category_are_not_automatically_merged():
    left = {
        "title": "Explosion at a market in northern Iraq",
        "country_code": "IQ", "category": "armed_conflict", "subcategory": "bombing",
        "event_time": "2026-11-27T04:00:00Z",
    }
    right = {
        "title": "Parliament approves new budget in Iraq",
        "country_code": "IQ", "category": "political_development", "subcategory": "legislative_development",
        "event_time": "2026-11-27T04:30:00Z",
    }
    result = compare_events(left, right)
    assert result.decision != SAME_EVENT


def test_two_separate_incidents_in_same_country_are_related_not_merged():
    left = {
        "title": "Airstrike hits military base in Ukraine",
        "country_code": "UA", "category": "armed_conflict", "subcategory": "airstrike",
        "event_time": "2026-11-27T04:00:00Z",
    }
    right = {
        "title": "Airstrike damages power station in Ukraine",
        "country_code": "UA", "category": "armed_conflict", "subcategory": "airstrike",
        "event_time": "2026-11-27T09:00:00Z",
    }
    result = compare_events(left, right)
    assert result.decision in {RELATED_EVENT, INDEPENDENT_EVENT}


def test_unrelated_events_are_independent():
    left = {"title": "Flood in Brazil", "country_code": "BR", "category": "natural_disaster",
            "event_time": "2026-11-27T04:00:00Z"}
    right = {"title": "Election in Norway", "country_code": "NO", "category": "political_development",
             "event_time": "2026-11-27T04:00:00Z"}
    assert compare_events(left, right).decision == INDEPENDENT_EVENT


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------
def test_single_report_is_newly_detected():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state, reason = derive_event_state(
        created_at=now.isoformat(), last_seen_at=now.isoformat(),
        report_count=1, independent_publishers=1,
    )
    assert state == "newly_detected"
    assert reason


def test_no_resolution_without_evidence():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    state, _ = derive_event_state(
        created_at=(now - timedelta(days=2)).isoformat(),
        last_seen_at=(now - timedelta(hours=30)).isoformat(),
        report_count=5, independent_publishers=3,
        recent_report_count=0, previous_report_count=5,
    )
    assert state not in {"resolved"}


def test_resolution_requires_explicit_evidence():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    state, _ = derive_event_state(
        created_at=now, last_seen_at=now, report_count=4,
        independent_publishers=2, resolution_evidence=True,
    )
    assert state == "resolved"


# ----------------------------------------------------------------------
# Assessment assembly
# ----------------------------------------------------------------------
def test_build_event_assessment_returns_all_three_measurements():
    independence = IndependenceAssessment(
        independent_publishers=2, syndicated_publishers=1,
        publisher_families=["reuters", "bbc"],
        duplicate_pairs=[], notes=[],
    )
    result = build_event_assessment(
        event={
            "id": 1, "category": "natural_disaster", "subcategory": "earthquake",
            "country_code": "JP", "location_precision": "city",
            "occurred_at_precision": "timestamp", "classification_confidence": 0.9,
            "created_at": "2026-11-27T03:00:00Z", "last_seen_at": "2026-11-27T05:00:00Z",
            "event_state": "newly_detected", "article_count": 1,
        },
        articles=[
            {"publisher_domain": "reuters.com", "reporting_type": "direct"},
            {"publisher_domain": "bbc.com", "reporting_type": "direct"},
            {"publisher_domain": "outlet.com", "reporting_type": "aggregated"},
        ],
        independence=independence,
        reported_casualties=5,
    )
    assert result["severity"]["score"] is not None
    assert result["confidence"]["score"] is not None
    assert result["priority"]["score"] is not None
    assert result["corroboration_level"] == "corroborated"
    assert result["confidence_explanation"]["summary"]
    assert 1 <= result["importance"] <= 10
