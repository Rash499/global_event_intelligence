"""Provider adapter lifecycle, failure isolation, scheduler and full ingestion flow.

No test touches the network: every provider read is patched. This is the
integration workflow the platform promises.
"""

from __future__ import annotations

import asyncio

import pytest

from app.ingestion.providers.base import (
    DEGRADED,
    DISABLED,
    NOT_CONFIGURED,
    UNAVAILABLE,
    CollectionResult,
    SourceProvider,
)


class RecordingProvider(SourceProvider):
    key = "recording"
    name = "Recording provider"
    provider_type = "news"
    produces_structured_observations = False

    def __init__(self, records=None, fail_times=0, config=None):
        super().__init__(config)
        self.records = records or []
        self.fail_times = fail_times
        self.calls = 0

    async def fetch_raw(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("upstream exploded")
        return self.records


def _article(title, url, published="2026-11-27T04:00:00Z", source="Example Wire"):
    return {
        "title": title,
        "url": url,
        "source": source,
        "published_at": published,
        "description": title,
    }


# ----------------------------------------------------------------------
# Adapter lifecycle
# ----------------------------------------------------------------------
def test_provider_normalises_records():
    provider = RecordingProvider([_article("Flooding in Colombo", "https://x.example/1")])
    result = asyncio.run(provider.collect())
    assert result.status == "healthy"
    assert result.records_received == 1
    assert result.records_accepted == 1
    assert result.articles[0]["canonical_url"] == "https://x.example/1"
    assert result.articles[0]["provider"] == "recording"


def test_provider_rejects_invalid_records():
    provider = RecordingProvider([{"title": "No URL"}, {"url": "https://x.example/2"}])
    result = asyncio.run(provider.collect())
    assert result.records_received == 2
    assert result.records_accepted == 0
    assert result.records_rejected == 2


def test_provider_retries_then_succeeds():
    provider = RecordingProvider([_article("Recovered feed", "https://x.example/3")], fail_times=2)
    result = asyncio.run(provider.collect())
    # Recovering after retries is reported as degraded, not healthy: the
    # failures are recorded so the health view can show them.
    assert result.status == DEGRADED
    assert provider.calls == 3
    assert len(result.errors) == 2  # failures are recorded, not swallowed
    assert provider.health().status in {"healthy", "degraded"}


def test_provider_failure_is_reported_as_unavailable():
    provider = RecordingProvider(fail_times=99)
    result = asyncio.run(provider.collect())
    assert result.status == UNAVAILABLE
    assert result.errors
    assert provider.health().status in {UNAVAILABLE, DEGRADED}


def test_circuit_breaker_opens_after_repeated_failures(monkeypatch):
    from app.config import Settings

    config = Settings(
        provider_max_retries=1,
        provider_circuit_failure_threshold=2,
        provider_circuit_cooldown_seconds=60,
    )
    provider = RecordingProvider(fail_times=99, config=config)
    asyncio.run(provider.collect())
    asyncio.run(provider.collect())
    assert provider.circuit_is_open() is True

    calls_before = provider.calls
    result = asyncio.run(provider.collect())
    assert result.status == UNAVAILABLE
    assert provider.calls == calls_before  # no request while the circuit is open


def test_unconfigured_provider_is_not_an_error():
    from app.ingestion.providers.structured import FirmsWildfireProvider

    provider = FirmsWildfireProvider()
    satisfied, note = provider.validate_config()
    assert satisfied is False
    assert "MAP_KEY" in note
    result = asyncio.run(provider.collect())
    assert result.status in {NOT_CONFIGURED, DISABLED}


def test_disabled_provider_reports_disabled():
    from app.ingestion.providers.structured import AcledProvider

    provider = AcledProvider()
    assert provider.is_enabled() is False
    assert asyncio.run(provider.collect()).status == DISABLED


def test_never_attempted_provider_is_idle_not_healthy():
    provider = RecordingProvider()
    assert provider.health().status == "idle"


# ----------------------------------------------------------------------
# Structured providers
# ----------------------------------------------------------------------
def test_usgs_observation_normalisation():
    from app.ingestion.providers.structured import UsgsEarthquakeProvider

    provider = UsgsEarthquakeProvider()
    observation = provider.normalise(
        {
            "record_id": "us7000abc",
            "title": "M6.5 earthquake — 10 km S of Tokyo, Japan",
            "place": "10 km S of Tokyo, Japan",
            "magnitude": 6.5,
            "magnitude_type": "mww",
            "depth_km": 35.0,
            "event_time": "2026-11-27T03:00:00Z",
            "observed_at": "2026-11-27T03:10:00Z",
            "latitude": 35.5,
            "longitude": 139.6,
            "source_url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abc",
        }
    )
    assert observation["category"] == "natural_disaster"
    assert observation["subcategory"] == "earthquake"
    assert observation["location_precision"] == "exact"
    assert observation["latitude"] == 35.5
    assert observation["attributes"]["magnitude"] == 6.5
    assert observation["country_code"] == "JP"
    assert observation["severity_hint"] > 5


def test_who_don_json_payload_parsing_and_normalisation():
    """WHO retired the DON RSS feed (404); the provider must parse the
    OData JSON API shape verified against who.int on 2026-11-27."""
    from app.ingestion.providers.structured import WhoOutbreakProvider, _parse_who_payload

    records = _parse_who_payload(
        {
            "@odata.context": "http://www.who.int/api/news/$metadata#diseaseoutbreaknews",
            "value": [
                {
                    "Id": "older-guid",
                    "Title": "Ebola disease outbreak - Uganda",
                    "Summary": "WHO was notified of an outbreak of Ebola disease in Uganda.",
                    "PublicationDateAndTime": "2026-11-20T19:00:00Z",
                    "ItemDefaultUrl": "/2026-DON100",
                    "UrlName": "2026-DON100",
                },
                {
                    "Id": "newer-guid",
                    "Title": "Influenza A(H5N1) - United States of America",
                    "Summary": "Three laboratory-confirmed human infections were notified.",
                    "PublicationDateAndTime": "2026-11-24T19:00:00Z",
                    "ItemDefaultUrl": "/2026-DON629",
                    "UrlName": "2026-DON629",
                },
            ],
        },
        max_entries=30,
    )
    # Newest first regardless of the server's ordering.
    assert [record["record_id"] for record in records] == ["2026-DON629", "2026-DON100"]
    assert records[0]["url"] == (
        "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON629"
    )

    observation = WhoOutbreakProvider().normalise(records[1])
    assert observation["category"] == "public_health"
    assert observation["subcategory"] == "disease_outbreak"
    # The DON API has no geography: the country comes from the title text.
    assert observation["country_code"] == "UG"
    assert observation["location_precision"] == "country"
    assert observation["attributes"]["disease_reported_in_text"] == ["ebola"]


def test_who_default_endpoint_is_the_json_api_not_the_retired_rss():
    from app.config import Settings

    assert Settings().who_api_url == "https://www.who.int/api/news/diseaseoutbreaknews"


def test_eonet_payload_parsing_and_normalisation():
    from app.ingestion.providers.structured import EonetProvider, _parse_eonet_payload

    records = _parse_eonet_payload(
        {
            "events": [
                {
                    "id": "EONET_9001",
                    "title": "Wildfire near Redding, California",
                    "description": "A wildfire reported by satellite sensors.",
                    "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_9001",
                    "closed": None,
                    "categories": [{"id": "wildfires", "title": "Wildfires"}],
                    "sources": [{"id": "EO", "url": "https://example.org/src"}],
                    "geometry": [
                        {"date": "2026-11-25T00:00:00Z", "type": "Point", "coordinates": [-122.4, 40.6]},
                        {"date": "2026-11-27T00:00:00Z", "type": "Point", "coordinates": [-122.3, 40.7]},
                    ],
                }
            ]
        },
        max_events=10,
    )
    assert len(records) == 1
    # Most recent Point geometry wins, stored exactly as reported.
    assert records[0]["latitude"] == 40.7 and records[0]["longitude"] == -122.3

    observation = EonetProvider().normalise(records[0])
    assert observation["category"] == "natural_disaster"
    assert observation["subcategory"] == "wildfire"
    assert observation["location_precision"] == "exact"
    assert observation["attributes"]["eonet_category"] == "wildfires"
    assert observation["provider"] == "eonet"


def test_eonet_earthquake_magnitude_becomes_severity_hint():
    from app.ingestion.providers.structured import EonetProvider

    observation = EonetProvider().normalise(
        {
            "record_id": "EONET_9002",
            "title": "Earthquake in Japan region",
            "category_id": "earthquakes",
            "magnitude_value": 6.0,
            "magnitude_unit": "M",
            "geometry_date": "2026-11-27T00:00:00Z",
            "latitude": 36.0,
            "longitude": 138.0,
            "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_9002",
        }
    )
    assert observation["subcategory"] == "earthquake"
    assert observation["severity_hint"] > 5
    assert observation["country_code"] == "JP"


def test_gdacs_payload_parsing_and_normalisation():
    from app.ingestion.providers.structured import GdacsProvider, _parse_gdacs_payload

    records = _parse_gdacs_payload(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [106.8, -6.2]},
                    "properties": {
                        "eventid": 1234567,
                        "episodeid": 7654321,
                        "eventtype": "EQ",
                        "name": "Earthquake in Indonesia",
                        "country": "Indonesia",
                        "alertlevel": "Red",
                        "alertscore": 90,
                        "severity": {"value": 6.4, "unit": "M"},
                        "fromdate": "2026-11-27T01:00:00",
                        "todate": "2026-11-29T01:00:00",
                        "url": "https://www.gdacs.org/report.aspx?eventid=1234567",
                    },
                }
            ],
        },
        max_events=10,
    )
    assert len(records) == 1
    assert records[0]["latitude"] == -6.2 and records[0]["longitude"] == 106.8

    observation = GdacsProvider().normalise(records[0])
    assert observation["category"] == "natural_disaster"
    assert observation["subcategory"] == "earthquake"
    assert observation["location_precision"] == "exact"
    assert observation["country_code"] == "ID"
    # GDACS alert level is preserved as the official severity; the numeric
    # hint is a derived mapping, disclosed in attributes.
    assert observation["official_severity"] == "red"
    assert observation["severity_hint"] == 8.5
    assert observation["attributes"]["gdacs_alert_score"] == 90
    assert observation["attributes"]["is_official_alert"] is True


def test_new_free_providers_registered_enabled_and_scheduled():
    from app.ingestion.registry import PROVIDERS, provider_interval_seconds
    from app.scheduler.runner import schedule_state

    for key in ("eonet", "gdacs"):
        provider = PROVIDERS[key]
        # Both APIs are public and keyless: no credentials may be required.
        assert provider.requires_credentials is False
        assert provider.is_enabled() is True
        assert provider.validate_config() == (True, None)
        assert provider.produces_structured_observations is True
        # Live operation has not been exercised yet; it must not be claimed.
        assert provider.verification_status == "unverified"
    assert provider_interval_seconds("eonet") == 3600
    assert provider_interval_seconds("gdacs") == 1800
    jobs = {job["provider"] for job in schedule_state()["jobs"]}
    assert {"eonet", "gdacs"} <= jobs


def test_firms_detection_is_labelled_as_detection_not_incident():
    from app.config import Settings
    from app.ingestion.providers.structured import FirmsWildfireProvider

    provider = FirmsWildfireProvider(Settings(firms_enabled=True, firms_map_key="test"))
    observation = provider.normalise(
        {
            "latitude": "34.5", "longitude": "69.2", "acq_date": "2026-11-27",
            "acq_time": "0930", "confidence": "nominal", "bright_ti4": "340.2",
            "satellite": "N", "instrument": "VIIRS",
        }
    )
    assert observation["subcategory"] == "wildfire"
    assert observation["attributes"]["is_detection_not_incident"] is True
    assert "not a confirmed wildfire" in observation["summary"].lower()


def test_cap_alert_mapping_and_geometry():
    from app.ingestion.providers.structured import CapAlertProvider

    provider = CapAlertProvider()
    observation = provider.normalise(
        {
            "identifier": "alert-1",
            "sender": "National Weather Service",
            "sent": "2026-11-27T03:00:00Z",
            "effective": "2026-11-27T03:00:00Z",
            "severity": "Extreme",
            "urgency": "Immediate",
            "certainty": "Observed",
            "headline": "Flash flood warning",
            "description": "Move to higher ground.",
            "polygon": "34.0,69.0 34.5,69.5 34.2,69.8",
            "centroid_latitude": 34.23,
            "centroid_longitude": 69.43,
            "category_mapped": "natural_disaster",
            "subcategory": "flood",
            "feed_url": "https://alerts.example/cap.xml",
        }
    )
    assert observation["official_severity"] == "extreme"
    assert observation["attributes"]["is_official_alert"] is True
    assert observation["location_precision"] == "exact"


# ----------------------------------------------------------------------
# Scheduler
# ----------------------------------------------------------------------
def test_scheduler_state_reports_independent_jobs():
    from app.scheduler.runner import schedule_state

    state = schedule_state()
    assert state["jobs"]
    providers = {job["provider"] for job in state["jobs"]}
    assert {"rss", "gdelt", "usgs"} <= providers
    assert all("interval_seconds" in job for job in state["jobs"])


# ----------------------------------------------------------------------
# Full ingestion workflow
# ----------------------------------------------------------------------
def test_ingestion_end_to_end_creates_events_with_assessments(db_path, monkeypatch):
    from app.database.db import get_connection
    from app.ingestion import service
    from app.ingestion.registry import PROVIDERS

    class FakeNews(SourceProvider):
        key = "rss"
        name = "Fake RSS"
        provider_type = "news"
        produces_structured_observations = False

        async def collect(self, trigger="manual"):
            records = [
                _article("Magnitude 6.8 earthquake strikes central Japan, tsunami advisory issued",
                         "https://www.bbc.com/news/japan-quake", source="BBC"),
                _article("Japan quake: magnitude 6.8 hits central Honshu",
                         "https://www.reuters.com/world/japan-quake", source="Reuters"),
                _article("Kenya protests over fuel prices enter third day",
                         "https://www.aljazeera.com/news/kenya-protests", source="Al Jazeera"),
            ]
            articles = [self.normalise(record) for record in records]
            return CollectionResult(
                provider=self.key, status="healthy",
                records_received=len(records), records_accepted=len(articles),
                articles=articles,
            ).finish()

    monkeypatch.setitem(PROVIDERS, "rss", FakeNews())
    result = asyncio.run(service.ingest(providers=["rss"]))

    assert result["articles_inserted"] == 3
    assert result["events_created"] >= 1

    conn = get_connection()
    try:
        events = [dict(row) for row in conn.execute(
            "SELECT * FROM events ORDER BY id"
        ).fetchall()]
        articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        timeline = conn.execute("SELECT COUNT(*) FROM event_timeline").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0]
        linked = conn.execute("SELECT COUNT(*) FROM event_articles").fetchone()[0]
    finally:
        conn.close()

    assert articles == 3
    assert linked == 3
    assert timeline >= 1
    assert runs == 1
    assert all(event["severity"] is not None for event in events)
    assert all(event["confidence"] is not None for event in events)
    assert all(event["event_state"] for event in events)
    assert all(event["confidence_components"] for event in events)
    # The two Japan reports must land on one event with two publishers.
    japan = [event for event in events if event["country_code"] == "JP"]
    assert len(japan) == 1
    assert japan[0]["article_count"] == 2
    assert japan[0]["independent_source_count"] >= 2


def test_one_failing_provider_does_not_stop_the_others(db_path, monkeypatch):
    from app.ingestion import service
    from app.ingestion.registry import PROVIDERS

    class GoodProvider(SourceProvider):
        key = "rss"
        name = "Good"
        provider_type = "news"

        async def collect(self, trigger="manual"):
            article = self.normalise(_article("Flooding in Colombo", "https://x.example/good"))
            return CollectionResult(
                provider="rss", status="healthy", records_received=1,
                records_accepted=1, articles=[article],
            ).finish()

    class BadProvider(SourceProvider):
        key = "gdelt"
        name = "Bad"
        provider_type = "news"

        async def collect(self, trigger="manual"):
            raise RuntimeError("provider down")

    monkeypatch.setitem(PROVIDERS, "rss", GoodProvider())
    monkeypatch.setitem(PROVIDERS, "gdelt", BadProvider())

    result = asyncio.run(service.ingest(providers=["rss", "gdelt"]))
    assert result["articles_inserted"] == 1
    statuses = {item["provider"]: item["status"] for item in result["providers"]}
    assert statuses["rss"] == "healthy"
    assert statuses["gdelt"] == "unavailable"


def test_duplicate_articles_are_not_stored_twice(db_path, monkeypatch):
    from app.ingestion import service
    from app.ingestion.registry import PROVIDERS

    records = [
        _article("Major flooding in Japan", "https://a.example/1?utm_source=rss"),
        _article("Major flooding in Japan", "https://a.example/1"),
    ]

    class DuplicatingProvider(SourceProvider):
        key = "rss"
        name = "Duplicating"
        provider_type = "news"

        async def collect(self, trigger="manual"):
            articles = [self.normalise(record) for record in records]
            return CollectionResult(
                provider="rss", status="healthy", records_received=2,
                records_accepted=2, articles=articles,
            ).finish()

    monkeypatch.setitem(PROVIDERS, "rss", DuplicatingProvider())
    result = asyncio.run(service.ingest(providers=["rss"]))
    assert result["articles_inserted"] == 1
    assert result["duplicates_removed"] == 1


def test_structured_observation_updates_existing_event(db_path):
    from app.database.db import get_connection
    from app.ingestion.service import _upsert_structured_observation
    from app.database.db import write_connection

    observation = {
        "provider": "usgs", "provider_record_id": "us123",
        "title": "M5.5 earthquake — off the coast of Japan",
        "summary": "USGS reports a magnitude 5.5 earthquake.",
        "category": "natural_disaster", "subcategory": "earthquake",
        "event_time": "2026-11-27T03:00:00Z", "latitude": 35.0, "longitude": 140.0,
        "location_precision": "exact", "country": "Japan", "country_code": "JP",
        "severity_hint": 6.0, "attributes": {"magnitude": 5.5},
        "publisher": "USGS", "observed_at": "2026-11-27T03:05:00Z",
    }
    with write_connection() as conn:
        first_id, created = _upsert_structured_observation(conn, observation)
        second_id, created_again = _upsert_structured_observation(conn, observation)

    assert created is True
    assert created_again is False
    assert first_id == second_id

    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


# ----------------------------------------------------------------------
# Ingestion performance indexes (dedupe + event matching candidates)
# ----------------------------------------------------------------------
def _raw_article(title, url, published_at, provider="rss", provider_record_id=None,
                 publisher="BBC", publisher_domain="bbc.com", description=""):
    return {
        "title": title,
        "url": url,
        "source": publisher,
        "publisher": publisher,
        "publisher_domain": publisher_domain,
        "provider": provider,
        "provider_record_id": provider_record_id,
        "published_at": published_at,
        "description": description or title,
        "content_hash": None,
    }


def test_dedupe_index_matches_full_scan_verdicts(db_path):
    """The candidate index must reproduce the full pairwise scan exactly.

    Covers the paths the index is allowed to skip: exact URL, exact title
    (window-independent), fuzzy title inside/outside the 48h window,
    provider-record identity, and clean inserts.
    """
    from app.database.db import get_connection
    from app.ingestion import service

    t0 = "2026-11-27T04:00:00Z"
    records = [
        _raw_article("Magnitude 6.8 earthquake strikes central Japan",
                     "https://bbc.example/quake-1", t0),
        # exact canonical-URL re-collection
        _raw_article("Magnitude 6.8 earthquake strikes central Japan",
                     "https://bbc.example/quake-1", t0),
        # exact title, far outside the fuzzy window: still a duplicate
        _raw_article("Magnitude 6.8 earthquake strikes central Japan",
                     "https://bbc.example/quake-old", "2026-08-01T04:00:00Z"),
        # fuzzy title match inside the window (different publisher)
        _raw_article("Earthquake magnitude 6.8 strikes central Japan region",
                     "https://reuters.example/quake-2", "2026-11-27T05:00:00Z",
                     publisher="Reuters", publisher_domain="reuters.com"),
        # fuzzy-shaped title but outside the 48h window: NOT a duplicate
        _raw_article("Earthquake magnitude 6.8 strikes central Japan region",
                     "https://reuters.example/quake-late", "2026-08-01T05:00:00Z",
                     publisher="Reuters", publisher_domain="reuters.com"),
        # provider-record identity beats a completely different headline
        _raw_article("Harbor ferry sinks near Lisbon", "https://bbc.example/ferry",
                     t0, provider_record_id="rec-1"),
        _raw_article("Completely unrelated headline here", "https://bbc.example/other",
                     t0, provider_record_id="rec-1"),
        # clean insert
        _raw_article("Kenya protests over fuel prices enter third day",
                     "https://bbc.example/kenya", t0),
    ]

    def run(use_index: bool):
        conn = get_connection()
        try:
            conn.execute("DELETE FROM articles")
            conn.commit()
            existing: list[dict] = []
            index = service._ArticleDedupeIndex(existing) if use_index else None
            verdicts = []
            for record in records:
                _id, verdict = service.store_article(conn, dict(record), existing, index)
                verdicts.append((verdict["duplicate"], verdict.get("kind")))
            conn.commit()
            return verdicts, len(existing)
        finally:
            conn.close()

    scanned = run(use_index=False)
    indexed = run(use_index=True)
    assert indexed == scanned
    # sanity on the expected shape of the sequence itself
    kinds = [kind for _dup, kind in indexed[0]]
    assert kinds[1] == "canonical_url"
    assert indexed[0][2][0] is True and indexed[0][4][0] is False
    assert indexed[1] == 4  # 8 records -> 4 stored articles


def test_event_candidate_index_covers_every_non_independent_decision():
    """Any pair compare_events calls same/related/similar must be indexed.

    Pairs judged independent may be skipped - that is the entire point of
    the candidate index - so the assertion is one-directional coverage.
    """
    from app.ingestion.service import _EventCandidateIndex
    from app.intelligence.clustering import INDEPENDENT_EVENT, compare_events

    events = [
        {"id": 1, "title": "Magnitude 6.8 earthquake strikes central Japan",
         "country_code": "JP", "category": "natural_disaster", "subcategory": "earthquake",
         "latitude": 36.2, "longitude": 138.25, "location_precision": "city",
         "event_time": "2026-11-27T03:00:00Z"},
        {"id": 2, "title": "Kenya protests over fuel prices enter third day",
         "country_code": "KE", "category": "politics", "subcategory": "protest",
         "latitude": -1.29, "longitude": 36.82, "location_precision": "city",
         "event_time": "2026-11-27T03:00:00Z"},
        {"id": 3, "title": "Harbor ferry sinks near Lisbon port",
         "country_code": "PT", "category": "accident", "subcategory": "maritime",
         "latitude": 38.72, "longitude": -9.14, "location_precision": "exact",
         "event_time": "2026-11-27T03:00:00Z"},
    ]
    index = _EventCandidateIndex([dict(event) for event in events])

    payloads = [
        # same incident as event 1, reworded (shared anchors/tokens)
        {"title": "Japan quake: magnitude 6.8 hits central Honshu",
         "country_code": "JP", "category": "natural_disaster", "subcategory": "earthquake",
         "latitude": 36.0, "longitude": 138.0, "location_precision": "city",
         "event_time": "2026-11-27T04:00:00Z"},
        # same country + theme as event 2 within the related window
        {"title": "Fuel price demonstrations spread to Mombasa",
         "country_code": "KE", "category": "politics", "subcategory": "protest",
         "latitude": -4.05, "longitude": 39.67, "location_precision": "city",
         "event_time": "2026-11-28T04:00:00Z"},
        # geographically close to event 3, no shared wording or country
        {"title": "Capsized vessel rescue operation under way",
         "country_code": "", "category": "accident", "subcategory": "maritime",
         "latitude": 38.9, "longitude": -9.3, "location_precision": "exact",
         "event_time": "2026-11-27T04:30:00Z"},
        # wholly unrelated: must be judged independent of everything
        {"title": "Parliament passes annual budget in Ottawa",
         "country_code": "CA", "category": "politics", "subcategory": "legislation",
         "latitude": 45.42, "longitude": -75.69, "location_precision": "city",
         "event_time": "2026-11-27T04:00:00Z"},
    ]

    for payload in payloads:
        candidates = index.candidate_ids(payload)
        for event in events:
            decision = compare_events(payload, event).decision
            if decision != INDEPENDENT_EVENT:
                assert event["id"] in candidates, (payload["title"], event["title"], decision)

    # The unrelated payload is a candidate for nothing.
    assert index.candidate_ids(payloads[3]) == set()
