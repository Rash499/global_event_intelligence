from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.intelligence.classification import normalize_category, classify_article
from app.intelligence.confidence import score_event_confidence
from app.intelligence.deduplication import is_duplicate
from app.intelligence.importance import score_event_importance
from app.main import app
from app.intelligence.verification import determine_corroboration_level


client = TestClient(app)


def test_same_url_is_duplicate():
    article = {"url": "https://example.com/flood", "title": "Flooding in Japan", "source": "Reuters"}
    assert is_duplicate(article, article) is True


def test_similar_title_is_possible_duplicate():
    a = {"url": "https://example.com/flood-1", "title": "Major flooding in Japan", "source": "Reuters", "published_at": "2025-01-01T12:00:00Z"}
    b = {"url": "https://example.com/flood-2", "title": "Flooding hits Japan causing emergency", "source": "BBC", "published_at": "2025-01-01T13:00:00Z"}
    assert is_duplicate(a, b) is True


def test_different_event_is_not_duplicate():
    a = {"url": "https://example.com/flood", "title": "Flooding in Japan", "source": "Reuters"}
    b = {"url": "https://example.com/election", "title": "Election results announced in Japan", "source": "AP"}
    assert is_duplicate(a, b) is False


def test_normalize_category_handles_known_name():
    assert normalize_category("Natural Disaster") == "natural_disaster"
    assert normalize_category("nonsense") == "other"


def test_classification_uses_fallback_for_unrecognized_value():
    result = classify_article({"title": "Flooding causes major disruption in Japan", "description": "Flood waters forced evacuations"})
    assert result["category"] == "natural_disaster"


def test_higher_impact_event_scores_higher():
    low = score_event_importance({"severity": 2, "geographic_impact": 1, "source_coverage": 1, "human_impact": 1, "economic_impact": 1, "urgency": 2})
    high = score_event_importance({"severity": 9, "geographic_impact": 8, "source_coverage": 7, "human_impact": 9, "economic_impact": 6, "urgency": 8})
    assert high > low


def test_multiple_sources_increase_confidence():
    single = score_event_confidence({"source_count": 1, "article_count": 1, "classification_confidence": 0.7, "location_confidence": 0.8, "time_confidence": 0.7})
    multiple = score_event_confidence({"source_count": 5, "article_count": 8, "classification_confidence": 0.9, "location_confidence": 0.9, "time_confidence": 0.9})
    assert multiple > single


def test_multiple_independent_sources_have_stronger_corroboration():
    assert determine_corroboration_level(1) == "single"
    assert determine_corroboration_level(2) == "corroborated"
    assert determine_corroboration_level(5) == "strong"


def test_statistics_overview_includes_timeline_and_category_breakdown():
    response = client.get("/api/statistics/overview")

    assert response.status_code == 200
    payload = response.json()

    assert "total_events" in payload
    assert "categories" in payload
    assert "countries_by_event_count" in payload
    assert "timeline" in payload
    assert isinstance(payload["timeline"], list)
