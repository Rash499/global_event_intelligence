from datetime import datetime, timedelta, timezone

from app.intelligence.source_catalog import credibility_score, source_metadata
from app.intelligence.importance import calculate_importance_score
from app.alerts.evaluator import alert_gate_decision
from app.intelligence.anomaly import WelfordBaseline, _keyword_spikes, severity_band_for_z
from app.intelligence.country_risk import calculate_country_risk, risk_level
from app.ingestion.registry import freshness_status, silent_zero_detected
from app.ingestion.providers.news import RssProvider
from app.intelligence.digest_cache import invalidate_snapshots, read_snapshot, write_snapshot
from app.intelligence.convergence import spatial_score


def test_unknown_source_is_not_treated_as_tier_four():
    result = source_metadata("unlisted-independent.example")
    assert result["source_tier"] == "undeclared"
    assert result["state_affiliated"] is False


def test_state_affiliated_feed_defaults_are_opt_in():
    from types import SimpleNamespace
    provider = RssProvider(config=SimpleNamespace(rss_include_state_affiliated=False))
    assert "Al Jazeera" not in provider.feeds
    assert "DW World" not in provider.feeds
    opted_in = RssProvider(config=SimpleNamespace(rss_include_state_affiliated=True))
    assert "Al Jazeera" in opted_in.feeds


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
    assert alert_gate_decision(_alert_event(now, severity=5), now=now)[1] == "severity_floor"
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


def test_anomaly_z_score_bands():
    assert severity_band_for_z(1.49) is None
    assert severity_band_for_z(1.5) == "medium"
    assert severity_band_for_z(2.0) == "high"
    assert severity_band_for_z(3.0) == "critical"


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


def test_keyword_spike_compares_recent_terms_to_seven_day_history(conn):
    now = datetime.now(timezone.utc)
    for days_ago in range(2, 9):
        stamp = (now - timedelta(days=days_ago)).isoformat()
        conn.execute("INSERT INTO events(title,category,created_at) VALUES(?,?,?)", ("Tension escalation reported", "armed_conflict", stamp))
    for _ in range(4):
        stamp = now.isoformat()
        conn.execute("INSERT INTO events(title,category,created_at) VALUES(?,?,?)", ("Tension escalation spreads", "armed_conflict", stamp))
    spikes = _keyword_spikes(conn, now)
    terms = {item["key"] for item in spikes}
    assert "tension" in terms
    assert "escalation" in terms


def test_spatial_convergence_score_and_critical_thresholds():
    assert spatial_score(3, 3) == (81, "high")
    assert spatial_score(3, 8) == (91, "critical")
    assert spatial_score(4, 1) == (102, "critical")


def test_country_risk_level_thresholds():
    assert [risk_level(value) for value in (0, 30, 31, 50, 51, 65, 66, 80, 81, 100)] == [
        "Low", "Low", "Normal", "Normal", "Elevated", "Elevated", "High", "High", "Critical", "Critical"
    ]


def test_country_score_formula_and_coverage_warning():
    result = calculate_country_risk("XX", [], 0, 0, {"countries": {}, "default": 20})
    assert result["score"] == 8.0
    assert result["level"] == "Low"
    assert result["coverage"]["warning"]


def test_country_provider_boosts_are_capped_and_components_are_exposed():
    events = [{"category": "armed_conflict", "severity": 8, "provider_keys": "usgs,firms,gdacs,eonet,reliefweb,who"} for _ in range(20)]
    result = calculate_country_risk("AA", events, 40, 12, {"countries": {}, "default": 35})
    assert result["components"]["conflict"] > 0
    assert result["boosts"]["usgs_earthquakes"]["score"] <= 8
    assert result["boosts"]["firms_wildfires"]["score"] <= 8
    assert result["boosts"]["disasters"]["score"] <= 8
    assert result["boosts"]["humanitarian"]["score"] <= 6
    assert result["boosts"]["outbreaks"]["score"] <= 6


def test_provider_freshness_thresholds_with_fake_clock():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    fresh_at = (now - timedelta(minutes=10)).isoformat()
    aging_at = (now - timedelta(hours=1)).isoformat()
    stale_at = (now - timedelta(hours=3)).isoformat()
    very_stale_at = (now - timedelta(hours=7)).isoformat()
    assert freshness_status(enabled=False, last_status=None, last_success_at=None, now=now, fresh_after=900, stale_after=7200, very_stale_after=21600)[0] == "disabled"
    assert freshness_status(enabled=True, last_status="unavailable", last_success_at=None, now=now, fresh_after=900, stale_after=7200, very_stale_after=21600)[0] == "error"
    assert freshness_status(enabled=True, last_status=None, last_success_at=None, now=now, fresh_after=900, stale_after=7200, very_stale_after=21600)[0] == "no_data"
    assert freshness_status(enabled=True, last_status="healthy", last_success_at=fresh_at, now=now, fresh_after=900, stale_after=7200, very_stale_after=21600)[0] == "fresh"
    assert freshness_status(enabled=True, last_status="healthy", last_success_at=aging_at, now=now, fresh_after=900, stale_after=7200, very_stale_after=21600)[0] == "aging"
    assert freshness_status(enabled=True, last_status="healthy", last_success_at=stale_at, now=now, fresh_after=900, stale_after=7200, very_stale_after=21600)[0] == "stale"
    assert freshness_status(enabled=True, last_status="healthy", last_success_at=very_stale_at, now=now, fresh_after=900, stale_after=7200, very_stale_after=21600)[0] == "very_stale"
    assert silent_zero_detected(3) and not silent_zero_detected(2)


def test_digest_snapshot_cache_age_and_invalidation(conn):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    write_snapshot("test-digest", {"items": [1, 2]}, generated_at=now - timedelta(minutes=2))
    cached = read_snapshot("test-digest", max_age_seconds=900, now=now)
    assert cached["cache_age_seconds"] == 120
    assert cached["items"] == [1, 2]
    assert read_snapshot("test-digest", max_age_seconds=60, now=now) is None
    invalidate_snapshots()
    assert read_snapshot("test-digest", now=now) is None
