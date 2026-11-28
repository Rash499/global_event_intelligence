from datetime import datetime, timedelta, timezone

from app.intelligence.source_catalog import credibility_score, source_metadata
from app.intelligence.importance import calculate_importance_score


def test_unknown_source_is_not_treated_as_tier_four():
    result = source_metadata("unlisted-independent.example")
    assert result["source_tier"] == "undeclared"
    assert result["state_affiliated"] is False


def test_catalog_marks_state_affiliation_and_research_region():
    result = source_metadata("feeds.bbci.co.uk")
    assert result["source_tier"] == 2
    assert result["region"] if "region" in result else result["source_region"] == "United Kingdom"


def test_credibility_includes_independent_corroboration_but_not_truth_claim():
    lone = [{"publisher_domain": "one.example", "source_tier": 2, "propaganda_risk": "low", "is_independent": 1}]
    multi = lone + [{"publisher_domain": "two.example", "source_tier": 2, "propaganda_risk": "low", "is_independent": 1}]
    assert credibility_score(multi) > credibility_score(lone)


def test_importance_caps_sources_at_six():
    items = [{"publisher_domain": f"{i}.example", "source_tier": "undeclared"} for i in range(9)]
    result = calculate_importance_score({"severity": 3}, items)
    assert result["components"]["source_count"] == 6


def test_importance_has_entity_corroboration_bonus():
    event = {"severity": 4}
    one = calculate_importance_score(event, [], ["A"])["score"]
    two = calculate_importance_score(event, [], ["A", "B"])["score"]
    assert two > one


def test_importance_source_tier_bonus():
    tier_one = calculate_importance_score({"severity": 3}, [{"source_tier": 1}])["score"]
    undeclared = calculate_importance_score({"severity": 3}, [{"source_tier": "undeclared"}])["score"]
    assert tier_one > undeclared


def test_flashpoint_interaction_increases_keyword_contribution():
    result = calculate_importance_score({"severity": 2, "title": "Border clash escalates after military attack"}, [])
    assert result["components"]["flashpoint_interaction"] is True


def test_recency_floor_and_linear_decay():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = calculate_importance_score({"severity": 3, "occurred_at": (now - timedelta(hours=2)).isoformat()}, [], now=now)
    old = calculate_importance_score({"severity": 3, "occurred_at": (now - timedelta(hours=30)).isoformat()}, [], now=now)
    assert recent["components"]["recency_multiplier"] > old["components"]["recency_multiplier"]
    assert old["components"]["recency_multiplier"] == 0.5


def test_corporate_financial_noise_is_demoted_without_entity_or_strong_classifier():
    data = {"severity": 4, "title": "Stock market shares rise after quarterly earnings"}
    result = calculate_importance_score(data, [])
    assert result["components"]["financial_noise_demoted"] is True
    assert result["score"] < calculate_importance_score({"severity": 4}, [])["score"]


def test_strong_non_keyword_classifier_prevents_financial_demote():
    result = calculate_importance_score({"severity": 4, "title": "Shares rise", "classification_method": "ai_assisted", "classification_confidence": 0.9}, [])
    assert result["components"]["financial_noise_demoted"] is False
