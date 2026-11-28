"""Context providers added in Phase 8 (all free; see docs/data-sources.md).

These follow the same pattern as the structured providers: published
schemas, pure payload parsers (fixture-tested offline), graceful
disable, and ``unverified`` until a real collection succeeds from a
deployment with outbound access. None of them needs a paid service;
the only credential anywhere here is UCDP's *free* access token, and
that provider stays off and ``not_configured`` until it is supplied.

Honesty rules:

* UNHCR figures are annual statistics, stored as country-level
  displacement context — never as incident pins.
* OFAC data is reduced to per-country entry counts (sanctions-pressure
  context). The list itself is not republished.
* State Department advisories are a US government assessment,
  republished as context and labelled as such; they also feed the
  country-risk advisory floor.
* Polymarket prices are market context set by traders. They are
  labelled ``is_our_prediction: false`` everywhere and are off by
  default.
* GPS/GNSS jamming is intentionally not implemented: no free, stable,
  attributable public feed could be verified; the system does not
  infer jamming from unrelated data.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..http import async_client, bounded_text
from ..normalize import clean_text, parse_timestamp, to_utc_iso
from .base import SourceProvider
from .structured import _observation

logger = logging.getLogger(__name__)


def _country_code(name: str | None) -> tuple[str | None, str | None]:
    """Resolve a country name to (name, code) from the repo gazetteer."""
    if not name:
        return None, None
    from ...intelligence.geolocation import COUNTRY_BY_NAME, NAME_ALIASES

    key = str(name).strip().lower()
    entry = COUNTRY_BY_NAME.get(key)
    if entry:
        return entry["name"], entry["code"]
    code = NAME_ALIASES.get(key)
    if code:
        from ...intelligence.geolocation import COUNTRY_BY_CODE

        entry = COUNTRY_BY_CODE.get(code)
        if entry:
            return entry["name"], entry["code"]
    return None, None


# ----------------------------------------------------------------------
# UCDP georeferenced conflict events (free data; free token for the API)
# ----------------------------------------------------------------------
UCDP_TYPE_MAP = {1: "armed_clash", 2: "armed_clash", 3: "extremist_violence"}


def _ucdp_severity(deaths) -> float:
    try:
        value = float(deaths or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 100:
        return 9.5
    if value >= 25:
        return 8.5
    if value >= 10:
        return 7.5
    if value >= 1:
        return 6.0
    return 4.0


def _parse_ucdp_payload(payload: dict) -> list[dict]:
    records = []
    for item in payload.get("Result") or []:
        records.append(
            {
                "record_id": item.get("id"),
                "date_start": item.get("date_start"),
                "country": item.get("country"),
                "region": item.get("adm_1"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "deaths_best": item.get("deaths_best"),
                "type_of_violence": item.get("type_of_violence"),
                "side_a": item.get("side_a"),
                "side_b": item.get("side_b"),
            }
        )
    return records


class UcdpProvider(SourceProvider):
    """UCDP GED conflict events. Free data; the API needs a free token."""

    key = "ucdp"
    name = "UCDP conflict events"
    provider_type = "conflict"
    docs_url = "https://ucdp.uu.se/downloads/"
    requires_credentials = True
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 86400

    def is_enabled(self) -> bool:
        return bool(self.config.ucdp_enabled)

    def validate_config(self) -> tuple[bool, str | None]:
        if not self.config.ucdp_access_token.strip():
            return (
                False,
                "UCDP data is free, but the GED API requires a free access "
                "token (register at https://ucdp.uu.se). Set UCDP_ACCESS_TOKEN "
                "to enable; the provider stays off and not_configured until then.",
            )
        return True, None

    async def fetch_raw(self) -> list[dict]:
        async with async_client(
            headers={"x-ucdp-access-token": self.config.ucdp_access_token}
        ) as client:
            response = await client.get(
                self.config.ucdp_api_url,
                params={"pagesize": max(1, self.config.ucdp_page_size), "page": 0},
            )
            response.raise_for_status()
            return _parse_ucdp_payload(response.json())

    def normalise(self, record: dict) -> dict | None:
        if record.get("record_id") is None:
            return None
        country, country_code = _country_code(record.get("country"))
        deaths = record.get("deaths_best")
        latitude, longitude = record.get("latitude"), record.get("longitude")
        has_point = latitude is not None and longitude is not None
        title = (
            f"UCDP conflict event in {record.get('region') or country or 'unknown location'}"
            f" ({record.get('date_start') or 'date unknown'})"
        )
        return _observation(
            provider=self.key,
            record_id=str(record.get("record_id")),
            observed_at=to_utc_iso(parse_timestamp(record.get("date_start"))),
            event_time=to_utc_iso(parse_timestamp(record.get("date_start"))),
            latitude=float(latitude) if has_point else None,
            longitude=float(longitude) if has_point else None,
            location_precision="exact" if has_point else ("country" if country_code else "unknown"),
            country=country,
            country_code=country_code,
            location_text=record.get("region") or country,
            category="armed_conflict",
            subcategory=UCDP_TYPE_MAP.get(record.get("type_of_violence"), "armed_clash"),
            title=title,
            summary=(
                "UCDP Georeferenced Event Dataset record"
                + (f" with best fatality estimate {deaths}" if deaths is not None else "")
                + ". Research dataset record; severity derives from reported fatalities."
            ),
            severity_hint=_ucdp_severity(deaths),
            attributes={
                "fatalities": deaths,
                "type_of_violence": record.get("type_of_violence"),
                "side_a": record.get("side_a"),
                "side_b": record.get("side_b"),
                "dataset": "UCDP GED",
            },
            source="UCDP",
            publisher="UCDP",
            published_at=to_utc_iso(parse_timestamp(record.get("date_start"))),
            url="https://ucdp.uu.se/encyclopedia",
            language="en",
            is_structured=True,
        )


# ----------------------------------------------------------------------
# UNHCR displacement statistics (public API, no key)
# ----------------------------------------------------------------------
def _parse_unhcr_payload(payload: dict, max_countries: int) -> list[dict]:
    """Aggregate latest-year refugees/asylum-seekers per asylum country."""
    by_country: dict[str, dict] = {}
    for item in payload.get("items") or []:
        iso = (item.get("countryOfAsylumISO") or "").strip().upper()
        if not iso:
            continue
        year = item.get("year") or 0
        bucket = by_country.setdefault(
            iso,
            {
                "country_code": iso,
                "country": item.get("countryOfAsylum"),
                "year": year,
                "refugees": 0,
                "asylum_seekers": 0,
            },
        )
        if year < bucket["year"]:
            continue
        if year > bucket["year"]:
            bucket.update(year=year, refugees=0, asylum_seekers=0)
        bucket["refugees"] += int(item.get("refugees") or 0)
        bucket["asylum_seekers"] += int(item.get("asylumSeekers") or 0)
    records = sorted(
        by_country.values(),
        key=lambda r: -(r["refugees"] + r["asylum_seekers"]),
    )
    return records[: max(1, max_countries)]


def _unhcr_severity(total: int) -> float:
    if total >= 1_000_000:
        return 7.0
    if total >= 250_000:
        return 6.0
    if total >= 50_000:
        return 5.0
    if total >= 10_000:
        return 4.0
    return 3.0


class UnhcrProvider(SourceProvider):
    """UNHCR annual displacement statistics (public API, no key)."""

    key = "unhcr"
    name = "UNHCR displacement statistics"
    provider_type = "humanitarian"
    docs_url = "https://api.unhcr.org/docs/index.html"
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 86400

    def is_enabled(self) -> bool:
        return bool(self.config.unhcr_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(
                self.config.unhcr_api_url, params={"limit": 10000}
            )
            response.raise_for_status()
            return _parse_unhcr_payload(response.json(), self.config.unhcr_max_countries)

    def normalise(self, record: dict) -> dict | None:
        country_code = record.get("country_code")
        if not country_code:
            return None
        country, resolved_code = _country_code(record.get("country"))
        country_code = resolved_code or country_code
        country = country or record.get("country") or country_code
        total = int(record["refugees"]) + int(record["asylum_seekers"])
        return _observation(
            provider=self.key,
            record_id=f"unhcr-{country_code}-{record['year']}",
            event_time=None,
            location_precision="country",
            country=country,
            country_code=country_code,
            location_text=country,
            category="humanitarian",
            subcategory="displacement",
            title=(
                f"UNHCR {record['year']}: {country} hosts "
                f"{record['refugees']:,} refugees and {record['asylum_seekers']:,} asylum-seekers"
            ),
            summary=(
                "UNHCR annual population statistics (country-level context, "
                "not an incident). Figures are the latest published annual "
                "totals for people displaced across borders into this country."
            ),
            severity_hint=_unhcr_severity(total),
            attributes={
                "refugees": record["refugees"],
                "asylum_seekers": record["asylum_seekers"],
                "total_displaced": total,
                "statistics_year": record["year"],
                "is_annual_statistic": True,
            },
            source="UNHCR",
            publisher="UNHCR",
            url="https://www.unhcr.org/refugee-statistics/",
            language="en",
            is_structured=True,
        )


# ----------------------------------------------------------------------
# OFAC consolidated sanctions list (public download; counts only)
# ----------------------------------------------------------------------
def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_ofac_payload(xml_text: str, max_countries: int) -> list[dict]:
    """Count listed entries per address country. The list is not republished."""
    root = ET.fromstring(xml_text)
    counts: dict[str, int] = {}
    for entry in root.iter():
        if _local_name(entry.tag) != "sdnEntry":
            continue
        countries = {
            (node.text or "").strip()
            for node in entry.iter()
            if _local_name(node.tag) == "country" and node.text
        }
        for country in countries:
            counts[country] = counts.get(country, 0) + 1
    records = [
        {"country_name": name, "entries": count}
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    return records[: max(1, max_countries)]


class OfacSanctionsProvider(SourceProvider):
    """OFAC Consolidated List reduced to per-country entry counts."""

    key = "ofac"
    name = "OFAC sanctions list (country counts)"
    provider_type = "sanctions"
    docs_url = "https://ofac.treasury.gov/"
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 86400

    def is_enabled(self) -> bool:
        return bool(self.config.ofac_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(self.config.ofac_list_url)
            response.raise_for_status()
            text = bounded_text(response, limit=16_000_000)
        return _parse_ofac_payload(text, self.config.ofac_max_countries)

    def normalise(self, record: dict) -> dict | None:
        country, country_code = _country_code(record.get("country_name"))
        if not country_code:
            return None
        return _observation(
            provider=self.key,
            record_id=f"ofac-cons-{country_code}",
            event_time=None,
            location_precision="country",
            country=country,
            country_code=country_code,
            location_text=country,
            category="political_development",
            subcategory="sanctions",
            title=(
                f"OFAC consolidated list: {record['entries']} listed entries "
                f"with an address in {country}"
            ),
            summary=(
                "Sanctions-pressure context derived from the US Treasury OFAC "
                "Consolidated List (public download). Only the per-country "
                "entry count is stored; the list contents are not republished "
                "and a count is not an incident."
            ),
            severity_hint=3.0,
            attributes={
                "sanctions_entries": record["entries"],
                "list": "OFAC Consolidated (non-SDN)",
                "is_context_signal": True,
            },
            source="OFAC",
            publisher="US Treasury OFAC",
            url="https://ofac.treasury.gov/",
            language="en",
            is_structured=True,
        )


# ----------------------------------------------------------------------
# US State Department travel advisories (public RSS)
# ----------------------------------------------------------------------
_LEVEL_RE = re.compile(r"level\s*([1-4])", re.IGNORECASE)
_ADVISORY_SEVERITY = {4: 6.0, 3: 5.0, 2: 3.5, 1: 2.0}
ADVISORY_FLOORS = {4: 55.0, 3: 40.0}


def _parse_advisories_payload(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    records = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        fields = {_local_name(child.tag): (child.text or "").strip() for child in item}
        title = fields.get("title", "")
        match = _LEVEL_RE.search(title)
        if not match:
            continue
        country_name = re.split(r"[:\-–]", title, maxsplit=1)[0].strip()
        records.append(
            {
                "country_name": country_name,
                "level": int(match.group(1)),
                "title": title,
                "summary": fields.get("description", ""),
                "link": fields.get("link", ""),
                "published": fields.get("pubDate", ""),
            }
        )
    return records


class StateAdvisoriesProvider(SourceProvider):
    """US State Department travel advisories (public RSS, no key)."""

    key = "state_advisories"
    name = "US travel advisories"
    provider_type = "advisory"
    docs_url = "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html"
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 21600

    def is_enabled(self) -> bool:
        return bool(self.config.state_advisories_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(self.config.state_advisories_feed_url)
            response.raise_for_status()
            text = bounded_text(response)
        return _parse_advisories_payload(text)

    def normalise(self, record: dict) -> dict | None:
        country, country_code = _country_code(record.get("country_name"))
        if not country_code:
            return None
        level = record["level"]
        published = to_utc_iso(parse_timestamp(record.get("published")))
        return _observation(
            provider=self.key,
            record_id=f"us-advisory-{country_code}",
            observed_at=published,
            event_time=published,
            location_precision="country",
            country=country,
            country_code=country_code,
            location_text=country,
            category="other",
            subcategory="unclassified",
            title=clean_text(record.get("title"), 300) or f"US travel advisory: {country}",
            summary=(
                "US Department of State travel advisory — a US government "
                "assessment republished as context, not this platform's "
                f"assessment. {clean_text(record.get('summary'), 600)}"
            ),
            severity_hint=_ADVISORY_SEVERITY.get(level, 2.0),
            attributes={
                "advisory_level": level,
                "advisory_floor": ADVISORY_FLOORS.get(level),
                "issuer": "US Department of State",
                "is_government_assessment": True,
            },
            source="US State Department",
            publisher="US Department of State",
            published_at=published,
            url=record.get("link") or "https://travel.state.gov/",
            language="en",
            is_structured=True,
        )


# ----------------------------------------------------------------------
# Polymarket market context (public API, read-only, opt-in)
# ----------------------------------------------------------------------
GEOPOLITICS_KEYWORDS = (
    "war", "ceasefire", "invasion", "strike", "election", "nuclear",
    "sanctions", "missile", "coup", "blockade", "hostage", "treaty",
)


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except ValueError:
            return []
    return []


def _parse_polymarket_payload(payload, max_markets: int) -> list[dict]:
    items = payload if isinstance(payload, list) else payload.get("markets") or []
    records = []
    for item in items:
        question = clean_text(item.get("question"), 300)
        if not question:
            continue
        lowered = question.lower()
        if not any(keyword in lowered for keyword in GEOPOLITICS_KEYWORDS):
            continue
        records.append(
            {
                "record_id": str(item.get("id") or item.get("slug") or question[:40]),
                "question": question,
                "outcomes": _json_list(item.get("outcomes")),
                "outcome_prices": _json_list(item.get("outcomePrices")),
                "volume": item.get("volume"),
                "slug": item.get("slug"),
            }
        )
        if len(records) >= max(1, max_markets):
            break
    return records


class PolymarketProvider(SourceProvider):
    """Polymarket public market context. Read-only; never our prediction."""

    key = "polymarket"
    name = "Polymarket market context (read-only)"
    provider_type = "context"
    docs_url = "https://docs.polymarket.com/api-reference/introduction"
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 3600

    def is_enabled(self) -> bool:
        # Opt-in context signal: market prices are not reporting.
        return bool(self.config.polymarket_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(
                self.config.polymarket_api_url,
                params={
                    "active": "true",
                    "closed": "false",
                    "order": "volume",
                    "ascending": "false",
                    "limit": 100,
                },
            )
            response.raise_for_status()
            return _parse_polymarket_payload(response.json(), self.config.polymarket_max_markets)

    def normalise(self, record: dict) -> dict | None:
        return _observation(
            provider=self.key,
            record_id=record.get("record_id"),
            event_time=None,
            location_precision="unknown",
            category="other",
            subcategory="unclassified",
            title=record.get("question") or "Polymarket market",
            summary=(
                "Read-only market context from Polymarket's public API. "
                "Prices are set by market participants; this is not a "
                "prediction by this platform and not verified intelligence."
            ),
            severity_hint=None,
            attributes={
                "context_signal": "polymarket_market",
                "is_our_prediction": False,
                "outcomes": record.get("outcomes"),
                "outcome_prices": record.get("outcome_prices"),
                "volume": record.get("volume"),
            },
            source="Polymarket",
            publisher="Polymarket",
            url=(
                f"https://polymarket.com/market/{record['slug']}"
                if record.get("slug")
                else "https://polymarket.com/"
            ),
            language="en",
            is_structured=True,
        )
