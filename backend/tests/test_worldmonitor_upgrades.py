from datetime import datetime, timedelta, timezone

from app.intelligence.source_catalog import credibility_score, source_metadata
from app.intelligence.importance import calculate_importance_score
from app.alerts.evaluator import alert_gate_decision
from app.intelligence.anomaly import WelfordBaseline


def test_unknown_source_is_not_treated_as_tier_four():
    result = source_metadata("unlisted-independent.example")
    assert result["source_tier"] == "undeclared"
    assert result["state_affiliated"] is False


def test_catalog_marks_state_affiliation_and_research_region():
    result = source_metadata("feeds.bbci.co.uk")
    assert result["source_tier"] == 2
    assert result["source_region"] == "United Kingdom"


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


def _alert_event(now, **overrides):
    return {"severity": 9, "importance_score": 80, "occurred_at": now.isoformat(), **overrides}


def test_alert_recency_gate_uses_fake_clock():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    ok, reason = alert_gate_decision(_alert_event(now - timedelta(minutes=16)), now=now)
    assert (ok, reason) == (False, "recency_gate")


def test_alert_importance_floor_and_severity_sensitivity():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert alert_gate_decision(_alert_event(now, importance_score=29), now=now)[1] == "importance_floor"
    assert alert_gate_decision(_alert_event(now, severity=7), now=now, sensitivity="critical_only")[1] == "user_sensitivity"


def test_alert_tier_gate_requires_non_keyword_classifier_for_tier_three_plus():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    event = _alert_event(now, classification_method="deterministic")
    assert alert_gate_decision(event, now=now, source_tier="3", has_news_source=True)[1] == "source_tier_gate"
    event["classification_method"] = "ai_assisted"
    assert alert_gate_decision(event, now=now, source_tier="3", has_news_source=True)[0] is True


def test_alert_story_phase_and_event_dedup_gates():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert alert_gate_decision(_alert_event(now), now=now, story_phase="fading")[1] == "story_phase_gate"
    assert alert_gate_decision(_alert_event(now), now=now, last_event_alert_at=now - timedelta(minutes=5))[1] == "event_dedup"


def test_global_cooldown_and_critical_override_only_for_high():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    recent_alert = now - timedelta(seconds=20)
    assert alert_gate_decision(_alert_event(now, severity=7), now=now, last_global_alert_at=recent_alert, last_global_severity=7)[1] == "global_cooldown"
    assert alert_gate_decision(_alert_event(now, severity=9), now=now, last_global_alert_at=recent_alert, last_global_severity=7)[0] is True
    assert alert_gate_decision(_alert_event(now, severity=9), now=now, last_global_alert_at=recent_alert, last_global_severity=9)[1] == "global_cooldown"


def test_welford_weekday_buckets_capture_seasonality_and_cold_start():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monday = WelfordBaseline()
    tuesday = WelfordBaseline()
    for week in range(12):
        monday.add(start + timedelta(days=week * 7), 8 + (week % 2), now=start + timedelta(days=week * 7))
        tuesday.add(start + timedelta(days=week * 7 + 1), 1 + (week % 2), now=start + timedelta(days=week * 7 + 1))
    assert monday.count == 12 and tuesday.count == 12
    assert monday.mean > tuesday.mean
    assert monday.z_score(20) is not None
    assert WelfordBaseline().z_score(100) is None


def test_welford_baseline_discards_samples_older_than_ninety_days():
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    baseline = WelfordBaseline()
    for day in range(120):
        stamp = now - timedelta(days=day)
        baseline.add(stamp, day, now=now)
    assert baseline.count == 90
