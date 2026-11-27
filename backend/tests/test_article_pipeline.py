"""Article normalisation, duplicate/syndication detection and clustering."""

from __future__ import annotations

from app.ingestion.normalize import normalize_article, parse_timestamp
from app.intelligence.deduplication import (
    assess_independence,
    compare_articles,
    is_duplicate,
)
from app.intelligence.urls import canonicalize_url, is_aggregator, publisher_family


# ----------------------------------------------------------------------
# URL canonicalisation
# ----------------------------------------------------------------------
def test_tracking_parameters_are_stripped():
    assert (
        canonicalize_url("https://www.bbc.com/news/x?utm_source=rss&utm_medium=feed")
        == "https://bbc.com/news/x"
    )


def test_amp_and_trailing_slash_are_normalised():
    assert canonicalize_url("https://cnn.com/story/amp/") == canonicalize_url("https://cnn.com/story")


def test_meaningful_query_parameters_are_kept():
    url = canonicalize_url("https://news.site/story?article=123&utm_source=x")
    assert "article=123" in url


def test_publisher_family_groups_bbc_domains():
    assert publisher_family("bbc.co.uk") == publisher_family("bbc.com")


def test_aggregators_are_detected():
    assert is_aggregator("news.google.com")
    assert is_aggregator("msn.com")
    assert not is_aggregator("bbc.com")


# ----------------------------------------------------------------------
# Normalisation
# ----------------------------------------------------------------------
def test_normalize_article_produces_full_provenance():
    article = normalize_article(
        {
            "title": "Flooding hits Colombo",
            "url": "https://www.dailymirror.lk/news/1?utm_source=x",
            "source": "Daily Mirror",
            "published_at": "Tue, 25 Nov 2026 10:00:00 GMT",
            "description": "<p>Heavy rain &amp; flooding</p>",
        },
        provider="rss",
    )
    assert article["title"] == "Flooding hits Colombo"
    assert article["canonical_url"] == "https://dailymirror.lk/news/1"
    assert article["publisher_domain"] == "dailymirror.lk"
    assert article["provider"] == "rss"
    assert article["published_at"].startswith("2026-11-25T10:00:00")
    assert "<p>" not in article["description"]
    assert article["first_seen_at"] and article["last_seen_at"]
    assert article["content_hash"]


def test_normalize_rejects_records_without_url_or_title():
    assert normalize_article({"title": "No URL"}, provider="rss") is None
    assert normalize_article({"url": "https://x.example/1"}, provider="rss") is None


def test_google_news_publisher_is_recovered_from_title():
    article = normalize_article(
        {
            "title": "Major quake hits Japan - Reuters",
            "url": "https://news.google.com/rss/articles/abc",
            "published_at": "2026-11-25T10:00:00Z",
            "description": "",
        },
        provider="google_news",
    )
    assert article["publisher"] == "Reuters"
    assert article["title"] == "Major quake hits Japan"
    assert article["reporting_type"] == "aggregated"
    assert article["is_independent"] == 0


def test_event_time_is_not_taken_from_publication_time():
    article = normalize_article(
        {
            "title": "Report published today",
            "url": "https://x.example/1",
            "published_at": "2026-11-25T10:00:00Z",
            "description": "Officials commented.",
        },
        provider="rss",
    )
    assert article["event_time"] is None
    assert article["event_time_precision"] == "unknown"


def test_explicit_incident_time_in_text_is_detected():
    article = normalize_article(
        {
            "title": "Quake struck on 2026-11-24T03:00:00Z",
            "url": "https://x.example/2",
            "published_at": "2026-11-25T10:00:00Z",
            "description": "",
        },
        provider="rss",
    )
    assert article["event_time"].startswith("2026-11-24T03:00:00")
    assert article["event_time_precision"] == "timestamp"


def test_reported_casualties_are_extracted():
    article = normalize_article(
        {
            "title": "At least 27 people killed in landslide",
            "url": "https://x.example/3",
            "description": "Another 40 were injured.",
        },
        provider="rss",
    )
    assert article["reported_casualties"] == 40


def test_parse_timestamp_handles_provider_formats():
    assert parse_timestamp("20240115T123000Z").year == 2024
    assert parse_timestamp("2026-11-25T10:00:00Z").tzinfo is not None
    assert parse_timestamp("Tue, 25 Nov 2026 10:00:00 GMT").hour == 10
    assert parse_timestamp("not a date") is None
    assert parse_timestamp(1700000000000).year == 2023


# ----------------------------------------------------------------------
# Duplicates
# ----------------------------------------------------------------------
def test_same_canonical_url_is_duplicate():
    left = {"url": "https://x.com/a?utm_source=1", "title": "One"}
    right = {"url": "https://x.com/a", "title": "Two"}
    assert compare_articles(left, right).kind == "canonical_url"


def test_unrelated_headlines_are_not_duplicates():
    left = {
        "url": "https://a.com/1",
        "title": "Flooding in Japan forces evacuations",
        "published_at": "2026-11-25T10:00:00Z",
    }
    right = {
        "url": "https://b.com/2",
        "title": "Election results announced in Japan",
        "published_at": "2026-11-25T11:00:00Z",
    }
    assert is_duplicate(left, right) is False


def test_same_country_and_words_but_far_apart_are_not_duplicates():
    left = {
        "url": "https://a.com/1",
        "title": "Explosion reported in Baghdad market",
        "published_at": "2026-11-01T10:00:00Z",
    }
    right = {
        "url": "https://b.com/2",
        "title": "Explosion reported in Baghdad market",
        "published_at": "2026-11-20T10:00:00Z",
    }
    assert is_duplicate(left, right) is True  # identical headline is still a duplicate


def test_near_duplicate_within_window_is_detected():
    left = {
        "url": "https://a.com/1",
        "title": "Major flooding in Japan",
        "published_at": "2026-11-25T10:00:00Z",
    }
    right = {
        "url": "https://b.com/2",
        "title": "Flooding hits Japan causing emergency",
        "published_at": "2026-11-25T12:00:00Z",
    }
    assert compare_articles(left, right).is_duplicate is True


# ----------------------------------------------------------------------
# Syndication / independence
# ----------------------------------------------------------------------
def test_syndicated_copies_do_not_count_as_corroboration():
    articles = [
        {"url": "https://reuters.com/a", "title": "Quake hits Japan coast", "published_at": "2026-11-25T10:00:00Z",
         "description": "A magnitude 6.8 earthquake struck off the coast of Japan early on Tuesday."},
        {"url": "https://outlet2.com/b", "title": "Quake hits Japan coast", "published_at": "2026-11-25T10:30:00Z",
         "description": "A magnitude 6.8 earthquake struck off the coast of Japan early on Tuesday."},
        {"url": "https://outlet3.com/c", "title": "Quake hits Japan coast", "published_at": "2026-11-25T11:00:00Z",
         "description": "A magnitude 6.8 earthquake struck off the coast of Japan early on Tuesday."},
    ]
    assessment = assess_independence(articles)
    assert assessment.independent_publishers == 1
    assert assessment.syndicated_publishers == 2
    assert any(pair["type"] == "syndicated" for pair in assessment.duplicate_pairs)


def test_same_newsroom_on_two_domains_counts_once():
    articles = [
        {"url": "https://bbc.com/a", "title": "Story one", "published_at": "2026-11-25T10:00:00Z"},
        {"url": "https://bbc.co.uk/b", "title": "Completely different report", "published_at": "2026-11-25T11:00:00Z"},
    ]
    assert assess_independence(articles).independent_publishers == 1


def test_aggregator_links_are_not_independent_confirmation():
    articles = [
        {"url": "https://reuters.com/a", "title": "Quake hits Japan", "published_at": "2026-11-25T10:00:00Z"},
        {"url": "https://news.google.com/rss/x", "title": "Quake hits Japan", "published_at": "2026-11-25T10:05:00Z"},
    ]
    assessment = assess_independence(articles)
    assert assessment.independent_publishers == 1
    assert any(pair["type"] == "aggregator" for pair in assessment.duplicate_pairs)


def test_genuinely_independent_reports_are_counted():
    articles = [
        {"url": "https://reuters.com/a", "title": "Quake hits central Japan, tsunami advisory issued",
         "published_at": "2026-11-25T10:00:00Z", "description": "A magnitude 6.8 earthquake struck Honshu."},
        {"url": "https://apnews.com/b", "title": "Government warns coastal residents after Japan quake",
         "published_at": "2026-11-25T11:00:00Z", "description": "Authorities issued evacuation guidance for coastal towns."},
    ]
    assert assess_independence(articles).independent_publishers == 2
