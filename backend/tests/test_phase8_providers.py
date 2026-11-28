"""Phase 8: free context providers (fixtures only; no network).

Master deferred these in docs/data-sources.md because endpoint
reachability could not be verified from the sandbox. They are now
implemented exactly along the revisit path that document names:
published schemas, offline fixtures, ``unverified`` until a real
collection succeeds, graceful disable, and key-requiring providers
off by default with a "requires free key" note.
"""

from __future__ import annotations

import asyncio


def test_ucdp_requires_free_token_and_is_off_by_default():
    from app.ingestion.providers.context import UcdpProvider, _parse_ucdp_payload

    provider = UcdpProvider()
    assert provider.is_enabled() is False
    satisfied, note = provider.validate_config()
    assert satisfied is False
    assert "free access token" in note
    assert provider.verification_status == "unverified"
    assert provider.requires_credentials is True

    records = _parse_ucdp_payload(
        {
            "Result": [
                {
                    "id": 991,
                    "date_start": "2026-03-04",
                    "country": "Ukraine",
                    "adm_1": "Donetsk",
                    "latitude": 48.0,
                    "longitude": 37.8,
                    "deaths_best": 30,
                    "type_of_violence": 1,
                    "side_a": "Government of Ukraine",
                    "side_b": "Separatist forces",
                }
            ]
        }
    )
    observation = provider.normalise(records[0])
    assert observation["category"] == "armed_conflict"
    assert observation["attributes"]["fatalities"] == 30
    assert observation["severity_hint"] == 8.5
    assert observation["country_code"] == "UA"
    assert observation["location_precision"] == "exact"


def test_unhcr_aggregates_latest_year_and_stays_country_level():
    from app.ingestion.providers.context import UnhcrProvider, _parse_unhcr_payload

    payload = {
        "items": [
            {"countryOfAsylumISO": "POL", "countryOfAsylum": "Poland", "year": 2023, "refugees": 900, "asylumSeekers": 10},
            {"countryOfAsylumISO": "POL", "countryOfAsylum": "Poland", "year": 2024, "refugees": 950000, "asylumSeekers": 5000},
            {"countryOfAsylumISO": "POL", "countryOfAsylum": "Poland", "year": 2024, "refugees": 1000, "asylumSeekers": 0},
            {"countryOfAsylumISO": "", "countryOfAsylum": "Nowhere", "year": 2024, "refugees": 5},
        ]
    }
    records = _parse_unhcr_payload(payload, 60)
    assert len(records) == 1
    assert records[0]["year"] == 2024
    assert records[0]["refugees"] == 951000

    observation = UnhcrProvider().normalise(records[0])
    # Annual statistics are country-level context, never incident pins.
    assert observation["location_precision"] == "country"
    assert observation["latitude"] is None
    assert observation["category"] == "humanitarian"
    assert observation["subcategory"] == "displacement"
    assert observation["attributes"]["is_annual_statistic"] is True


def test_ofac_reduces_list_to_country_counts_only():
    from app.ingestion.providers.context import OfacSanctionsProvider, _parse_ofac_payload

    xml = """<sdnList>
      <sdnEntry><lastName>Alpha Trading</lastName><addressList>
        <address><city>Moscow</city><country>Russia</country></address>
        <address><city>Dubai</city><country>United Arab Emirates</country></address>
      </addressList></sdnEntry>
      <sdnEntry><lastName>Beta Shipping</lastName><addressList>
        <address><city>Vladivostok</city><country>Russia</country></address>
      </addressList></sdnEntry>
    </sdnList>"""
    records = _parse_ofac_payload(xml, 120)
    by_country = {r["country_name"]: r["entries"] for r in records}
    assert by_country == {"Russia": 2, "United Arab Emirates": 1}

    observation = OfacSanctionsProvider().normalise(records[0])
    assert observation["subcategory"] == "sanctions"
    assert observation["country_code"] == "RU"
    assert observation["attributes"]["sanctions_entries"] == 2
    # The list contents are not republished: no entry names anywhere.
    assert "Alpha" not in observation["title"]
    assert "Alpha" not in observation["summary"]


def test_state_advisories_parse_levels_and_label_the_assessment():
    from app.ingestion.providers.context import StateAdvisoriesProvider, _parse_advisories_payload

    xml = """<rss version="2.0"><channel>
      <item><title>Ukraine: Level 4: Do Not Travel</title>
        <description>Do not travel to Ukraine due to armed conflict.</description>
        <pubDate>Mon, 10 Nov 2026 05:00:00 GMT</pubDate>
        <link>https://travel.state.gov/en/international-travel/travel-advisories/ukraine.html</link></item>
      <item><title>France: Level 2: Exercise Increased Caution</title>
        <description>Exercise increased caution.</description>
        <pubDate>Mon, 10 Nov 2026 05:00:00 GMT</pubDate><link>https://travel.state.gov/fr</link></item>
      <item><title>Some page without a level</title><description>x</description></item>
    </channel></rss>"""
    records = _parse_advisories_payload(xml)
    assert [r["level"] for r in records] == [4, 2]

    observation = StateAdvisoriesProvider().normalise(records[0])
    assert observation["country_code"] == "UA"
    assert observation["attributes"]["advisory_level"] == 4
    assert observation["attributes"]["advisory_floor"] == 55.0
    assert "US government" in observation["summary"]
    assert "not this platform's" in observation["summary"]


def test_polymarket_is_opt_in_context_and_never_our_prediction():
    from app.ingestion.providers.context import PolymarketProvider, _parse_polymarket_payload

    provider = PolymarketProvider()
    assert provider.is_enabled() is False  # opt-in context, off by default

    records = _parse_polymarket_payload(
        [
            {"id": "m1", "question": "Will a ceasefire be signed in 2027?", "outcomes": '["Yes","No"]', "outcomePrices": '["0.35","0.65"]', "volume": 50000, "slug": "ceasefire-2027"},
            {"id": "m2", "question": "Best picture winner?", "outcomes": '["A","B"]', "outcomePrices": '["0.5","0.5"]', "volume": 90000, "slug": "oscars"},
        ],
        40,
    )
    # Non-geopolitics markets are filtered out.
    assert [r["record_id"] for r in records] == ["m1"]

    observation = provider.normalise(records[0])
    assert observation["attributes"]["context_signal"] == "polymarket_market"
    assert observation["attributes"]["is_our_prediction"] is False
    assert "not a prediction by this platform" in observation["summary"]
    assert observation["location_precision"] == "unknown"
    assert observation["severity_hint"] is None


def test_new_providers_registered_with_honest_posture():
    from app.ingestion.registry import PROVIDERS

    for key in ("ucdp", "unhcr", "ofac", "state_advisories", "polymarket"):
        assert key in PROVIDERS
        assert PROVIDERS[key].verification_status == "unverified"
        assert PROVIDERS[key].produces_structured_observations is True


def test_unhcr_ingestion_end_to_end_stores_country_context(db_path, monkeypatch):
    from app.ingestion import service
    from app.ingestion.providers.context import UnhcrProvider
    from app.ingestion.registry import PROVIDERS

    class FakeUnhcr(UnhcrProvider):
        async def fetch_raw(self):
            return [
                {
                    "country_code": "POL",
                    "country": "Poland",
                    "year": 2024,
                    "refugees": 951000,
                    "asylum_seekers": 5000,
                }
            ]

    monkeypatch.setitem(PROVIDERS, "unhcr", FakeUnhcr())
    asyncio.run(service.ingest_provider("unhcr", trigger="test"))

    from app.database.db import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT country_code, location_precision, category FROM events WHERE provider_keys = 'unhcr'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["country_code"] == "PL"
    assert row["location_precision"] == "country"
    assert row["category"] == "humanitarian"


def test_structured_rerun_dedupes_and_keeps_provider_keys(db_path, monkeypatch):
    """Regression: recompute used to wipe provider_keys for structured
    events (no articles), which broke upsert dedupe on the next run and
    silently disabled provider boosts/floors keyed on provider_keys."""
    from app.ingestion import service
    from app.ingestion.providers.context import UnhcrProvider
    from app.ingestion.registry import PROVIDERS

    class FakeUnhcr(UnhcrProvider):
        async def fetch_raw(self):
            return [
                {
                    "country_code": "POL",
                    "country": "Poland",
                    "year": 2024,
                    "refugees": 951000,
                    "asylum_seekers": 5000,
                }
            ]

    monkeypatch.setitem(PROVIDERS, "unhcr", FakeUnhcr())
    asyncio.run(service.ingest_provider("unhcr", trigger="test"))
    asyncio.run(service.ingest_provider("unhcr", trigger="test"))

    from app.database.db import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT provider_keys FROM events WHERE category = 'humanitarian'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[0]["provider_keys"] == "unhcr"


def test_country_risk_floors_from_ingested_advisory_and_ucdp():
    from app.intelligence.country_risk import calculate_country_risk

    events = [
        {
            "category": "other",
            "severity": 6,
            "provider_keys": "state_advisories",
            "data_sources": '{"advisory_level": 4}',
        },
        {
            "category": "armed_conflict",
            "severity": 8,
            "provider_keys": "ucdp",
            "data_sources": '{"fatalities": 130}',
        },
    ]
    result = calculate_country_risk("XX", events, 0, 0, {"countries": {}, "default": 20})
    floors = " ".join(result["floors_applied"])
    assert "travel_advisory" in floors and "55" in floors
    assert "conflict_history" in floors and "45" in floors
    assert result["score"] >= 55.0  # advisory floor cannot be averaged away

    # No Phase-8 observations -> no floors, never invented.
    plain = calculate_country_risk("XX", [], 0, 0, {"countries": {}, "default": 20})
    assert plain["floors_applied"] == []
    assert plain["score"] == 8.0
