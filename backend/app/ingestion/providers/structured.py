"""Structured observation providers.

These return *events that already have structure* (magnitude, coordinates,
times) rather than news articles.  They set
``produces_structured_observations = True`` so the ingestion service routes them
through event upsert instead of article clustering.

Honesty rules enforced here:

* no coordinate is invented — USGS/FIRMS/CAP coordinates are stored exactly;
* a detection is not a confirmed incident (FIRMS thermal anomalies);
* an empty result is a valid result, not an error.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ..http import async_client, bounded_text
from ..normalize import clean_text, parse_timestamp, to_utc_iso
from .base import SourceProvider

logger = logging.getLogger(__name__)


def _observation(**kwargs) -> dict:
    base = {
        "kind": "structured_observation",
        "provider": kwargs.pop("provider"),
        "provider_record_id": kwargs.pop("record_id", None),
        "source_url": kwargs.pop("source_url", None),
        "observed_at": kwargs.pop("observed_at", None),
        "event_time": None,
        "event_time_precision": "timestamp",
        "latitude": None,
        "longitude": None,
        "location_precision": "exact",
        "country": None,
        "country_code": None,
        "location_text": None,
        "category": "other",
        "subcategory": "unclassified",
        "title": "",
        "summary": "",
        "severity_hint": None,
        "official_severity": None,
        "attributes": {},
    }
    base.update(kwargs)
    return base


# ----------------------------------------------------------------------
# USGS earthquakes
# ----------------------------------------------------------------------
class UsgsEarthquakeProvider(SourceProvider):
    key = "usgs"
    name = "USGS Earthquake Hazards"
    provider_type = "hazard"
    docs_url = "https://earthquake.usgs.gov/fdsnws/event/1/"
    produces_structured_observations = True
    default_interval_seconds = 600

    def is_enabled(self) -> bool:
        return bool(self.config.usgs_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(self.config.usgs_feed_url)
            response.raise_for_status()
            payload = response.json()

        features = payload.get("features") or []
        min_magnitude = float(self.config.usgs_min_magnitude)
        observations = []
        for feature in features[: max(1, self.config.usgs_max_features)]:
            props = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []
            magnitude = props.get("mag")
            if magnitude is not None:
                try:
                    if float(magnitude) < min_magnitude:
                        continue
                except (TypeError, ValueError):
                    pass

            lon = coordinates[0] if len(coordinates) > 0 else None
            lat = coordinates[1] if len(coordinates) > 1 else None
            depth = coordinates[2] if len(coordinates) > 2 else None
            place = clean_text(props.get("place"), 200) or "Unknown location"

            observations.append(
                {
                    "record_id": feature.get("id"),
                    "source_url": props.get("url"),
                    "observed_at": to_utc_iso(parse_timestamp(props.get("updated"))),
                    "event_time": to_utc_iso(parse_timestamp(props.get("time"))),
                    "latitude": float(lat) if lat is not None else None,
                    "longitude": float(lon) if lon is not None else None,
                    "title": f"M{magnitude} earthquake — {place}" if magnitude is not None else f"Earthquake — {place}",
                    "magnitude": magnitude,
                    "magnitude_type": props.get("magType"),
                    "depth_km": depth,
                    "place": place,
                    "status": props.get("status"),
                    "tsunami": props.get("tsunami"),
                    "alert_level": props.get("alert"),
                    "felt_reports": props.get("felt"),
                    "significance": props.get("sig"),
                }
            )
        return observations

    def normalise(self, record: dict) -> dict | None:
        from ...intelligence.geolocation import extract_location

        magnitude = record.get("magnitude")
        place = record.get("place") or ""
        location = extract_location(place)
        severity_hint = None
        if magnitude is not None:
            try:
                severity_hint = min(10.0, max(1.0, (float(magnitude) - 2.0) * 1.45 + 2.0))
            except (TypeError, ValueError):
                severity_hint = None

        attributes = {
            key: record.get(key)
            for key in (
                "magnitude", "magnitude_type", "depth_km", "place", "status",
                "tsunami", "alert_level", "felt_reports", "significance",
            )
            if record.get(key) is not None
        }

        summary_bits = [f"USGS reports a magnitude {magnitude}", f"near {place}"]
        if record.get("depth_km") is not None:
            summary_bits.append(f"at a depth of {record['depth_km']} km")
        if record.get("tsunami"):
            summary_bits.append("A tsunami flag was raised by USGS")

        return _observation(
            provider=self.key,
            record_id=record.get("record_id"),
            source_url=record.get("source_url"),
            observed_at=record.get("observed_at"),
            event_time=record.get("event_time"),
            latitude=record.get("latitude"),
            longitude=record.get("longitude"),
            location_precision="exact",
            country=location.country,
            country_code=location.country_code,
            location_text=place,
            category="natural_disaster",
            subcategory="earthquake",
            title=record.get("title") or "Earthquake",
            summary=". ".join(summary_bits) + ".",
            severity_hint=severity_hint,
            official_severity=record.get("alert_level"),
            attributes=attributes,
            source="USGS",
            publisher="USGS",
            published_at=record.get("event_time"),
            image_url=None,
            description=". ".join(summary_bits),
            language="en",
            url=record.get("source_url") or f"usgs://{record.get('record_id')}",
            is_structured=True,
        )


# ----------------------------------------------------------------------
# NASA EONET natural events
# ----------------------------------------------------------------------
# EONET v3 category id -> (taxonomy category, subcategory). The raw EONET
# category is always kept in attributes for auditability.
EONET_CATEGORY_MAP = {
    "earthquakes": ("natural_disaster", "earthquake"),
    "floods": ("natural_disaster", "flood"),
    "volcanoes": ("natural_disaster", "volcanic_activity"),
    "wildfires": ("natural_disaster", "wildfire"),
    "landslides": ("natural_disaster", "landslide"),
    "drought": ("natural_disaster", "drought"),
    "severeStorms": ("severe_weather", "severe_storm"),
    "tempExtremes": ("severe_weather", "extreme_heat"),
    "snow": ("severe_weather", "extreme_cold"),
    "dustHaze": ("environmental", "pollution_incident"),
    "seaLakeIce": ("environmental", "ecological_damage"),
    "waterColor": ("environmental", "ecological_damage"),
    "manmade": ("other", "unclassified"),
}


def _parse_eonet_payload(payload: dict, max_events: int) -> list[dict]:
    """Flatten an EONET v3 /events payload into raw records.

    Each event's position is its *most recent Point geometry* exactly as
    reported - coordinates are never derived. Events whose geometries are
    polygons only keep no coordinates; the normaliser may still place them
    at country level from their title text.
    """
    records = []
    for event in (payload.get("events") or [])[: max(1, max_events)]:
        points = [
            geometry
            for geometry in (event.get("geometry") or [])
            if (geometry or {}).get("type") == "Point"
            and len(geometry.get("coordinates") or []) >= 2
        ]
        latest = None
        if points:
            latest = max(points, key=lambda g: g.get("date") or "")
        categories = event.get("categories") or []
        category_id = (categories[0] or {}).get("id") if categories else None
        lon = latest["coordinates"][0] if latest else None
        lat = latest["coordinates"][1] if latest else None
        records.append(
            {
                "record_id": event.get("id"),
                "title": event.get("title"),
                "description": event.get("description"),
                "link": event.get("link"),
                "closed": event.get("closed"),
                "category_id": category_id,
                "geometry_date": latest.get("date") if latest else None,
                "magnitude_value": latest.get("magnitudeValue") if latest else None,
                "magnitude_unit": latest.get("magnitudeUnit") if latest else None,
                "latitude": float(lat) if lat is not None else None,
                "longitude": float(lon) if lon is not None else None,
                "sources": [
                    source.get("id") for source in (event.get("sources") or []) if source.get("id")
                ],
            }
        )
    return records


class EonetProvider(SourceProvider):
    """NASA EONET natural-event catalogue (public API, no key required).

    Implemented against the published v3 API shape and unit-tested with
    fixture payloads; live operation has not been exercised from the
    development sandbox, so the provider reports ``unverified`` until a
    real collection succeeds - the Providers page shows this honestly.
    """

    key = "eonet"
    name = "NASA EONET natural events"
    provider_type = "hazard"
    docs_url = "https://eonet.gsfc.nasa.gov/docs/v3"
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 3600

    def is_enabled(self) -> bool:
        return bool(self.config.eonet_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(
                f"{self.config.eonet_base_url.rstrip('/')}/events",
                params={
                    "status": "all",
                    "days": max(1, self.config.eonet_days),
                    "limit": max(1, self.config.eonet_max_events),
                },
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_eonet_payload(payload, self.config.eonet_max_events)

    def normalise(self, record: dict) -> dict | None:
        from ...intelligence.geolocation import extract_location

        title = clean_text(record.get("title"), 400)
        if not title or not record.get("record_id"):
            return None

        category, subcategory = EONET_CATEGORY_MAP.get(
            record.get("category_id") or "", ("other", "unclassified")
        )
        latitude, longitude = record.get("latitude"), record.get("longitude")
        has_point = latitude is not None and longitude is not None
        # Country is taken from the event's own title text only; coordinates
        # (when present) are EONET's, stored exactly.
        location = extract_location(title)
        description = clean_text(record.get("description"), 2000)

        severity_hint = None
        magnitude = record.get("magnitude_value")
        if record.get("category_id") == "earthquakes" and magnitude is not None:
            try:
                severity_hint = min(10.0, max(1.0, (float(magnitude) - 2.0) * 1.45 + 2.0))
            except (TypeError, ValueError):
                severity_hint = None

        status_note = "closed" if record.get("closed") else "ongoing"
        return _observation(
            provider=self.key,
            record_id=record.get("record_id"),
            source_url=record.get("link"),
            observed_at=to_utc_iso(parse_timestamp(record.get("geometry_date"))),
            event_time=to_utc_iso(parse_timestamp(record.get("geometry_date"))),
            latitude=latitude,
            longitude=longitude,
            location_precision="exact" if has_point else ("country" if location.country_code else "unknown"),
            country=location.country,
            country_code=location.country_code,
            location_text=location.location_text or title,
            category=category,
            subcategory=subcategory,
            title=title,
            summary=(
                description[:800]
                or f"NASA EONET catalogue entry ({status_note}): {title}."
            ),
            severity_hint=severity_hint,
            attributes={
                "eonet_category": record.get("category_id"),
                "eonet_sources": record.get("sources"),
                "eonet_status": status_note,
                "magnitude_value": magnitude,
                "magnitude_unit": record.get("magnitude_unit"),
                "is_catalogue_entry": True,
            },
            source="NASA EONET",
            publisher="NASA EONET",
            published_at=to_utc_iso(parse_timestamp(record.get("geometry_date"))),
            description=description or title,
            language="en",
            url=record.get("link") or f"https://eonet.gsfc.nasa.gov/api/v3/events/{record.get('record_id')}",
            is_structured=True,
        )


# ----------------------------------------------------------------------
# GDACS disaster alerts (UN / European Commission)
# ----------------------------------------------------------------------
GDACS_EVENT_TYPE_MAP = {
    "EQ": ("natural_disaster", "earthquake", "Earthquake"),
    "TC": ("natural_disaster", "tropical_cyclone", "Tropical cyclone"),
    "FL": ("natural_disaster", "flood", "Flood"),
    "VO": ("natural_disaster", "volcanic_activity", "Volcanic activity"),
    "DR": ("natural_disaster", "drought", "Drought"),
    "WF": ("natural_disaster", "wildfire", "Wildfire"),
    "TS": ("natural_disaster", "tsunami", "Tsunami"),
}

# GDACS alert levels mapped onto the platform's 0-10 severity hint scale.
# The original level and score are preserved in attributes/official_severity.
GDACS_ALERT_SEVERITY_HINT = {"red": 8.5, "orange": 6.0, "green": 3.5}


def _parse_gdacs_payload(payload, max_events: int) -> list[dict]:
    """Flatten a GDACS geteventlist payload (GeoJSON or bare list)."""
    if isinstance(payload, dict):
        features = payload.get("features") or payload.get("events") or []
    elif isinstance(payload, list):
        features = payload
    else:
        features = []

    records = []
    for feature in features[: max(1, max_events)]:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or feature
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        lon = coordinates[0] if len(coordinates) > 0 else None
        lat = coordinates[1] if len(coordinates) > 1 else None
        url = props.get("url") or props.get("link")
        if isinstance(url, dict):
            url = url.get("link") or url.get("href")
        records.append(
            {
                "event_id": props.get("eventid"),
                "episode_id": props.get("episodeid"),
                "event_type": (props.get("eventtype") or "").upper(),
                "name": props.get("name") or props.get("eventname") or props.get("title"),
                "country": props.get("country"),
                "alert_level": (props.get("alertlevel") or "").lower() or None,
                "alert_score": props.get("alertscore"),
                "severity_value": (props.get("severity") or {}).get("value")
                if isinstance(props.get("severity"), dict)
                else props.get("severity"),
                "severity_unit": (props.get("severity") or {}).get("unit")
                if isinstance(props.get("severity"), dict)
                else None,
                "from_date": props.get("fromdate"),
                "to_date": props.get("todate"),
                "modified_date": props.get("modifieddate"),
                "description": props.get("htmldescription") or props.get("description"),
                "url": url,
                "latitude": float(lat) if lat is not None else None,
                "longitude": float(lon) if lon is not None else None,
            }
        )
    return records


class GdacsProvider(SourceProvider):
    """GDACS disaster alerts (public REST API, no authentication required).

    Implemented against the published GDACS API shape and unit-tested with
    fixture payloads; live operation has not been exercised from the
    development sandbox, so the provider reports ``unverified`` until a
    real collection succeeds.
    """

    key = "gdacs"
    name = "GDACS disaster alerts"
    provider_type = "hazard"
    docs_url = "https://www.gdacs.org/gdacsapi/swagger/index.html"
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 1800

    def is_enabled(self) -> bool:
        return bool(self.config.gdacs_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(self.config.gdacs_api_url)
            response.raise_for_status()
            payload = response.json()
        return _parse_gdacs_payload(payload, self.config.gdacs_max_events)

    def normalise(self, record: dict) -> dict | None:
        from ...intelligence.geolocation import extract_location

        event_type = record.get("event_type") or ""
        if record.get("event_id") is None and not record.get("name"):
            return None
        category, subcategory, type_label = GDACS_EVENT_TYPE_MAP.get(
            event_type, ("natural_disaster", "unclassified", "Disaster")
        )
        country_name = clean_text(record.get("country"), 200)
        location = extract_location(country_name or record.get("name") or "")
        latitude, longitude = record.get("latitude"), record.get("longitude")
        has_point = latitude is not None and longitude is not None

        alert_level = record.get("alert_level")
        title = clean_text(record.get("name"), 400) or (
            f"{type_label} — {country_name}" if country_name else f"GDACS {type_label} alert"
        )
        description = clean_text(record.get("description"), 3000)
        report_url = record.get("url") or (
            "https://www.gdacs.org/report.aspx"
            f"?eventid={record.get('event_id')}&episodeid={record.get('episode_id')}"
        )

        return _observation(
            provider=self.key,
            record_id=f"{event_type}-{record.get('event_id')}",
            source_url=report_url,
            observed_at=to_utc_iso(parse_timestamp(record.get("modified_date"))),
            event_time=to_utc_iso(parse_timestamp(record.get("from_date"))),
            latitude=latitude,
            longitude=longitude,
            location_precision="exact" if has_point else ("country" if location.country_code else "unknown"),
            country=country_name or location.country,
            country_code=location.country_code,
            location_text=country_name or location.location_text,
            category=category,
            subcategory=subcategory,
            title=title,
            summary=description[:800] or f"GDACS {type_label} alert for {country_name or 'an area'} (alert level: {alert_level or 'not reported'}).",
            severity_hint=GDACS_ALERT_SEVERITY_HINT.get(alert_level or ""),
            official_severity=alert_level,
            attributes={
                "gdacs_event_type": event_type,
                "gdacs_alert_level": alert_level,
                "gdacs_alert_score": record.get("alert_score"),
                "gdacs_severity_value": record.get("severity_value"),
                "gdacs_severity_unit": record.get("severity_unit"),
                "gdacs_episode_id": record.get("episode_id"),
                "alert_end": record.get("to_date"),
                "is_official_alert": True,
            },
            source="GDACS",
            publisher="GDACS",
            published_at=to_utc_iso(parse_timestamp(record.get("from_date"))),
            description=description or title,
            language="en",
            url=report_url,
            is_structured=True,
        )


# ----------------------------------------------------------------------
# ReliefWeb humanitarian reports
# ----------------------------------------------------------------------
class ReliefWebProvider(SourceProvider):
    key = "reliefweb"
    name = "ReliefWeb humanitarian reports"
    provider_type = "humanitarian"
    docs_url = "https://apidoc.reliefweb.int/"
    requires_credentials = True
    produces_structured_observations = True
    default_interval_seconds = 3600

    def is_enabled(self) -> bool:
        return bool(self.config.reliefweb_enabled)

    def validate_config(self) -> tuple[bool, str | None]:
        if not self.config.reliefweb_appname.strip():
            return (
                False,
                "ReliefWeb API v2 requires a pre-approved `appname`. Request "
                "one via the form at https://apidoc.reliefweb.int/ (approval "
                "required since 1 Nov 2025; unapproved names get HTTP 403), "
                "then set RELIEFWEB_APPNAME.",
            )
        if "/v2" not in self.config.reliefweb_base_url:
            return (
                False,
                "RELIEFWEB_BASE_URL must point at the v2 API "
                "(https://api.reliefweb.int/v2); v1 is decommissioned.",
            )
        return True, None

    async def fetch_raw(self) -> list[dict]:
        limit = max(1, min(100, self.config.reliefweb_max_records))
        # v2: `appname` is sent in the URL only (GET and POST), not the body.
        payload = {
            "limit": limit,
            "preset": "latest",
            "fields": {
                "include": [
                    "title", "url", "body", "date.created", "date.original",
                    "source.name", "country.name", "country.iso3",
                    "disaster.name", "disaster.type.name", "primary_country.name",
                ]
            },
            "sort": ["date.created:desc"],
        }
        async with async_client() as client:
            response = await client.post(
                f"{self.config.reliefweb_base_url.rstrip('/')}/reports"
                f"?appname={quote(self.config.reliefweb_appname, safe='')}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        records = []
        for item in (data.get("data") or []):
            fields = item.get("fields") or {}
            country = (fields.get("primary_country") or {}) or {}
            if not country:
                countries = fields.get("country") or []
                country = countries[0] if countries else {}
            disasters = fields.get("disaster") or []
            records.append(
                {
                    "id": item.get("id"),
                    "title": fields.get("title"),
                    "url": fields.get("url"),
                    "body": fields.get("body"),
                    "created": (fields.get("date") or {}).get("created"),
                    "original": (fields.get("date") or {}).get("original"),
                    "sources": [s.get("name") for s in (fields.get("source") or []) if s.get("name")],
                    "country_name": country.get("name"),
                    "country_iso3": country.get("iso3"),
                    "disasters": [d.get("name") for d in disasters if d.get("name")],
                    "disaster_types": [
                        t.get("name")
                        for d in disasters
                        for t in (d.get("type") or [])
                        if t.get("name")
                    ],
                }
            )
        return records

    def normalise(self, record: dict) -> dict | None:
        url = record.get("url")
        title = clean_text(record.get("title"), 400)
        if not url or not title:
            return None

        from ...intelligence.geolocation import extract_location

        location = extract_location(record.get("country_name") or "")
        body = clean_text(record.get("body"), 4000)
        disaster_types = " ".join(record.get("disaster_types") or [])
        subcategory = "humanitarian_access"
        if "flood" in disaster_types.lower():
            subcategory = "displacement"
        if record.get("disasters"):
            category, subcategory = "humanitarian", "displacement"

        publisher = (record.get("sources") or ["ReliefWeb"])[0]
        return _observation(
            provider=self.key,
            record_id=record.get("id"),
            source_url=url,
            observed_at=record.get("created"),
            event_time=to_utc_iso(parse_timestamp(record.get("original"))),
            location_precision="country" if location.country_code else "unknown",
            country=record.get("country_name") or location.country,
            country_code=location.country_code,
            location_text=record.get("country_name"),
            category=category,
            subcategory=subcategory,
            title=title,
            summary=body[:800] or title,
            official_severity=None,
            attributes={
                "disasters": record.get("disasters"),
                "disaster_types": record.get("disaster_types"),
                "sources": record.get("sources"),
                "country_iso3": record.get("country_iso3"),
            },
            source=publisher,
            publisher=publisher,
            published_at=record.get("created"),
            description=body,
            language="en",
            url=url,
            is_structured=True,
        )


# ----------------------------------------------------------------------
# WHO Disease Outbreak News
# ----------------------------------------------------------------------
WHO_DON_ITEM_BASE = "https://www.who.int/emergencies/disease-outbreak-news/item"


def _parse_who_payload(payload, max_entries: int) -> list[dict]:
    """Flatten the WHO DON OData JSON payload into raw records.

    Response shape (verified against who.int, 2026-11-27):
    ``{"value": [{"Title", "Summary", "PublicationDateAndTime",
    "ItemDefaultUrl" ("/2026-DON629"), "UrlName", "Id", ...}]}``.
    The DON API has no geography; countries are read from the title text
    during normalisation, exactly as with the retired RSS feed.
    """
    if isinstance(payload, dict):
        items = payload.get("value") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    records = []
    for item in items:
        if not isinstance(item, dict):
            continue
        default_url = item.get("ItemDefaultUrl")
        url_name = item.get("UrlName")
        if isinstance(default_url, str) and default_url.startswith("http"):
            url = default_url
        elif isinstance(default_url, str) and default_url:
            url = WHO_DON_ITEM_BASE + (default_url if default_url.startswith("/") else f"/{default_url}")
        elif url_name:
            url = f"{WHO_DON_ITEM_BASE}/{url_name}"
        else:
            url = None
        published = to_utc_iso(
            parse_timestamp(item.get("PublicationDateAndTime") or item.get("PublicationDate"))
        )
        records.append(
            {
                "record_id": url_name or item.get("Id") or url,
                "title": item.get("Title"),
                "url": url,
                "summary": item.get("Summary"),
                "published": published,
            }
        )
    # Do not trust the server-side ordering: newest first, then cap.
    records.sort(key=lambda record: record.get("published") or "", reverse=True)
    return records[: max(1, max_entries)]


class WhoOutbreakProvider(SourceProvider):
    """WHO Disease Outbreak News via the public OData JSON API (no key).

    WHO retired the DON RSS feed (its URL returns 404), so this provider was
    migrated to ``https://www.who.int/api/news/diseaseoutbreaknews``. The
    live response shape was verified by direct inspection on 2026-11-27 and
    is covered by fixture tests, but no collection has run through this
    code path yet, so the provider reports ``unverified`` until one does.
    """

    key = "who"
    name = "WHO Disease Outbreak News"
    provider_type = "health"
    docs_url = "https://www.who.int/emergencies/disease-outbreak-news"
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 3600

    def is_enabled(self) -> bool:
        return bool(self.config.who_enabled)

    async def fetch_raw(self) -> list[dict]:
        async with async_client() as client:
            response = await client.get(
                self.config.who_api_url,
                params={
                    "$top": max(1, self.config.who_max_entries),
                    "$orderby": "PublicationDateAndTime desc",
                },
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_who_payload(payload, self.config.who_max_entries)

    def normalise(self, record: dict) -> dict | None:
        url = record.get("url")
        title = clean_text(record.get("title"), 400)
        if not url or not title:
            return None

        from ...intelligence.geolocation import extract_location

        summary = clean_text(record.get("summary"), 3000)
        location = extract_location(f"{title} {summary}")

        return _observation(
            provider=self.key,
            record_id=record.get("record_id") or url,
            source_url=url,
            observed_at=record.get("published"),
            event_time=to_utc_iso(parse_timestamp(record.get("published"))),
            location_precision="country" if location.country_code else "unknown",
            country=location.country,
            country_code=location.country_code,
            location_text=location.location_text,
            category="public_health",
            subcategory="disease_outbreak",
            title=title,
            summary=summary[:800] or title,
            attributes={"disease_reported_in_text": _disease_from_text(title)},
            source="WHO",
            publisher="WHO",
            published_at=record.get("published"),
            description=summary,
            language="en",
            url=url,
            is_structured=True,
        )


DISEASE_NAMES = (
    "cholera", "ebola", "measles", "dengue", "malaria", "polio", "mpox",
    "monkeypox", "yellow fever", "marburg", "influenza", "covid-19",
    "hepatitis", "meningitis", "plague", "diphtheria", "lassa fever",
)


def _disease_from_text(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [name for name in DISEASE_NAMES if name in lowered]


# ----------------------------------------------------------------------
# NASA FIRMS thermal anomalies
# ----------------------------------------------------------------------
class FirmsWildfireProvider(SourceProvider):
    key = "firms"
    name = "NASA FIRMS thermal anomalies"
    provider_type = "hazard"
    docs_url = "https://firms.modaps.eosdis.nasa.gov/api/"
    requires_credentials = True
    produces_structured_observations = True
    default_interval_seconds = 3600

    def is_enabled(self) -> bool:
        return bool(self.config.firms_enabled)

    def validate_config(self) -> tuple[bool, str | None]:
        if not self.config.firms_map_key.strip():
            return (
                False,
                "NASA FIRMS requires a free MAP_KEY "
                "(https://firms.modaps.eosdis.nasa.gov/api/map_key/). "
                "Set FIRMS_MAP_KEY to enable this provider.",
            )
        return True, None

    async def fetch_raw(self) -> list[dict]:
        url = (
            f"{self.config.firms_base_url}/{self.config.firms_map_key}/"
            f"{self.config.firms_source}/{self.config.firms_bbox}/"
            f"{max(1, self.config.firms_day_range)}"
        )
        async with async_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            text = bounded_text(response, limit=8_000_000)

        lines = [line for line in text.strip().splitlines() if line.strip()]
        if not lines:
            return []
        header = [column.strip() for column in lines[0].split(",")]
        records = []
        for line in lines[1:]:
            values = [value.strip() for value in line.split(",")]
            if len(values) < len(header):
                continue
            row = dict(zip(header, values))
            records.append(row)
        return records[: max(1, self.config.firms_max_detections)]

    def normalise(self, record: dict) -> dict | None:
        try:
            latitude = float(record.get("latitude"))
            longitude = float(record.get("longitude"))
        except (TypeError, ValueError):
            return None

        acq_date = record.get("acq_date") or ""
        acq_time = (record.get("acq_time") or "").zfill(4)
        event_time = None
        if acq_date:
            try:
                event_time = to_utc_iso(
                    datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M").replace(
                        tzinfo=timezone.utc
                    )
                )
            except ValueError:
                event_time = None

        confidence = record.get("confidence")
        brightness = record.get("bright_ti4") or record.get("brightness")
        satellite = record.get("satellite") or record.get("instrument")
        record_id = f"{satellite or 'firms'}-{latitude:.4f}-{longitude:.4f}-{event_time or ''}"

        return _observation(
            provider=self.key,
            record_id=record_id,
            source_url="https://firms.modaps.eosdis.nasa.gov/map/",
            observed_at=event_time,
            event_time=event_time,
            latitude=latitude,
            longitude=longitude,
            location_precision="exact",
            country=None,
            country_code=None,
            location_text=f"{latitude:.3f}, {longitude:.3f}",
            category="natural_disaster",
            subcategory="wildfire",
            title=f"Thermal anomaly detected ({satellite or 'satellite'}) at {latitude:.2f}, {longitude:.2f}",
            summary=(
                "NASA FIRMS thermal anomaly detection. A detection is not a "
                "confirmed wildfire incident; it indicates a heat signature "
                "consistent with fire."
            ),
            attributes={
                "confidence": confidence,
                "brightness": brightness,
                "satellite": satellite,
                "instrument": record.get("instrument"),
                "daynight": record.get("daynight"),
                "frp": record.get("frp"),
                "is_detection_not_incident": True,
            },
            source="NASA FIRMS",
            publisher="NASA FIRMS",
            published_at=event_time,
            description="Thermal anomaly detection",
            language="en",
            url=f"https://firms.modaps.eosdis.nasa.gov/map/#d:24hrs;@{longitude},{latitude},8z",
            is_structured=True,
        )


# ----------------------------------------------------------------------
# CAP emergency alerts
# ----------------------------------------------------------------------
class CapAlertProvider(SourceProvider):
    key = "cap"
    name = "Common Alerting Protocol feeds"
    provider_type = "emergency_alert"
    docs_url = "https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html"
    produces_structured_observations = True
    default_interval_seconds = 600

    def is_enabled(self) -> bool:
        return bool(self.config.cap_feed_url_list)

    def validate_config(self) -> tuple[bool, str | None]:
        if not self.config.cap_feed_url_list:
            return (
                False,
                "No CAP feed configured. Set CAP_FEED_URLS to a comma separated "
                "list of official CAP XML feeds.",
            )
        return True, None

    async def fetch_raw(self) -> list[dict]:
        records: list[dict] = []
        errors: list[str] = []
        async with async_client() as client:
            for url in self.config.cap_feed_url_list:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    root = ET.fromstring(bounded_text(response, limit=4_000_000))
                except (Exception,) as exc:  # noqa: BLE001 - per-feed isolation
                    errors.append(f"{url}: {type(exc).__name__}: {exc}")
                    continue

                for info in root.findall(".//{*}info"):
                    records.append(_parse_cap_info(root, info, url))
        if errors and not records:
            raise RuntimeError("; ".join(errors[:3]))
        return records

    def normalise(self, record: dict) -> dict | None:
        if not record.get("identifier"):
            return None
        polygon = record.get("polygon")
        latitude = record.get("centroid_latitude")
        longitude = record.get("centroid_longitude")
        precision = "exact" if latitude is not None and longitude is not None else "unknown"

        return _observation(
            provider=self.key,
            record_id=record.get("identifier"),
            source_url=record.get("feed_url"),
            observed_at=record.get("sent"),
            event_time=to_utc_iso(parse_timestamp(record.get("effective"))) or record.get("sent"),
            latitude=latitude,
            longitude=longitude,
            location_precision=precision,
            country=None,
            country_code=record.get("country_code"),
            location_text=record.get("area_description"),
            category=record.get("category_mapped") or "other",
            subcategory=record.get("subcategory") or "unclassified",
            title=record.get("headline") or record.get("event") or "Emergency alert",
            summary=clean_text(record.get("description"), 2000),
            official_severity=(record.get("severity") or "").lower() or None,
            attributes={
                "sender": record.get("sender"),
                "urgency": record.get("urgency"),
                "certainty": record.get("certainty"),
                "msg_type": record.get("msg_type"),
                "status": record.get("status"),
                "expires": record.get("expires"),
                "instruction": record.get("instruction"),
                "polygon": polygon,
                "is_official_alert": True,
            },
            source=record.get("sender") or "CAP",
            publisher=record.get("sender") or "CAP",
            published_at=record.get("sent"),
            description=clean_text(record.get("description"), 2000),
            language=record.get("language") or "en",
            url=record.get("feed_url"),
            is_structured=True,
        )


def _text(element, path: str) -> str | None:
    found = element.find(path)
    return found.text.strip() if found is not None and found.text else None


def _parse_cap_info(root, info, feed_url: str) -> dict:
    identifier = _text(info, "{*}identifier") or _text(root, "{*}identifier")
    event = _text(info, "{*}event")
    categories = [el.text for el in info.findall("{*}category") if el.text]
    areas = info.findall(".//{*}area")
    area_description = None
    polygon = None
    centroid_lat = centroid_lon = None

    for area in areas:
        area_description = area_description or _text(area, "{*}areaDesc")
        polygon_text = _text(area, "{*}polygon")
        if polygon_text and not polygon:
            polygon = polygon_text
            points = [tuple(map(float, pair.split(","))) for pair in polygon_text.split() if "," in pair]
            if points:
                centroid_lat = sum(p[0] for p in points) / len(points)
                centroid_lon = sum(p[1] for p in points) / len(points)
        if centroid_lat is None:
            circle = _text(area, "{*}circle")
            if circle and "," in circle:
                parts = circle.split()
                lat_lon = parts[0].split(",")
                if len(lat_lon) == 2:
                    try:
                        centroid_lat, centroid_lon = float(lat_lon[0]), float(lat_lon[1])
                    except ValueError:
                        pass

    category_mapped, subcategory = _map_cap_category(event, categories)

    return {
        "identifier": identifier,
        "sender": _text(info, "{*}senderName"),
        "sent": to_utc_iso(parse_timestamp(_text(root, "{*}sent") or _text(info, "{*}sent"))),
        "effective": _text(info, "{*}effective"),
        "expires": _text(info, "{*}expires"),
        "msg_type": _text(root, "{*}msgType"),
        "status": _text(root, "{*}status"),
        "urgency": _text(info, "{*}urgency"),
        "severity": _text(info, "{*}severity"),
        "certainty": _text(info, "{*}certainty"),
        "event": event,
        "headline": _text(info, "{*}headline"),
        "description": _text(info, "{*}description"),
        "instruction": _text(info, "{*}instruction"),
        "language": _text(info, "{*}language"),
        "area_description": area_description,
        "polygon": polygon,
        "centroid_latitude": centroid_lat,
        "centroid_longitude": centroid_lon,
        "category_mapped": category_mapped,
        "subcategory": subcategory,
        "feed_url": feed_url,
        "country_code": None,
    }


def _map_cap_category(event: str | None, categories: list[str]) -> tuple[str, str]:
    text = f"{event or ''} {' '.join(categories)}".lower()
    if any(word in text for word in ("fire", "wildfire")):
        return "natural_disaster", "wildfire"
    if any(word in text for word in ("flood", "rain")):
        return "natural_disaster", "flood"
    if any(word in text for word in ("earthquake", "tsunami")):
        return "natural_disaster", "earthquake" if "earthquake" in text else "tsunami"
    if any(word in text for word in ("cyclone", "hurricane", "typhoon", "storm")):
        return "natural_disaster", "tropical_cyclone"
    if any(word in text for word in ("heat", "cold", "weather", "wind", "snow")):
        return "severe_weather", "official_weather_warning"
    if any(word in text for word in ("health", "disease", "epidemic")):
        return "public_health", "disease_outbreak"
    if any(word in text for word in ("security", "terror", "law enforcement")):
        return "crime_public_safety", "public_safety_incident"
    if any(word in text for word in ("rescue", "evacuation", "hazard")):
        return "natural_disaster", "flood"
    return "other", "unclassified"


# ----------------------------------------------------------------------
# ACLED (credential-gated)
# ----------------------------------------------------------------------
class AcledProvider(SourceProvider):
    key = "acled"
    name = "ACLED conflict and protest data"
    provider_type = "conflict"
    docs_url = "https://acleddata.com/"
    requires_credentials = True
    # Implemented against ACLED's published API shape but never exercised
    # against a real myACLED account (access is licence/tier controlled).
    # Live operation is therefore unverified and must not be claimed.
    verification_status = "unverified"
    produces_structured_observations = True
    default_interval_seconds = 3600

    def is_enabled(self) -> bool:
        return bool(self.config.acled_enabled)

    def validate_config(self) -> tuple[bool, str | None]:
        if not self.config.acled_access_token.strip():
            return (
                False,
                "ACLED data is licence-controlled and requires registration and "
                "an access token. Set ACLED_ACCESS_TOKEN (and review ACLED's terms "
                "of use before redistributing data) to enable this provider.",
            )
        return True, None

    async def fetch_raw(self) -> list[dict]:
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        params = {
            "key": self.config.acled_access_token,
            "limit": 200,
            "event_date": week_ago,
            "event_date_where": ">=",
        }
        async with async_client() as client:
            response = await client.get(self.config.acled_base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        return (payload.get("data") or [])[:200]

    def normalise(self, record: dict) -> dict | None:
        event_date = record.get("event_date")
        if not event_date:
            return None
        category_map = {
            "Battles": ("armed_conflict", "armed_clash"),
            "Explosions/Remote violence": ("armed_conflict", "airstrike"),
            "Violence against civilians": ("terrorism_extremism", "extremist_violence"),
            "Protests": ("protest_unrest", "demonstration"),
            "Riots": ("protest_unrest", "riot"),
            "Strategic developments": ("political_development", "political_crisis"),
        }
        category, subcategory = category_map.get(
            record.get("event_type"), ("armed_conflict", "security_incident")
        )
        try:
            latitude = float(record.get("latitude"))
            longitude = float(record.get("longitude"))
            precision = "city" if record.get("geo_precision") in {"1", "2", 1, 2} else "admin_region"
        except (TypeError, ValueError):
            latitude = longitude = None
            precision = "country"

        return _observation(
            provider=self.key,
            record_id=record.get("event_id_cnty") or record.get("data_id"),
            source_url=record.get("source"),
            observed_at=event_date,
            event_time=to_utc_iso(parse_timestamp(event_date)),
            latitude=latitude,
            longitude=longitude,
            location_precision=precision,
            country=record.get("country"),
            country_code=record.get("iso"),
            location_text=record.get("location"),
            category=category,
            subcategory=subcategory,
            title=f"{record.get('event_type')} — {record.get('location')}, {record.get('country')}",
            summary=clean_text(record.get("notes"), 1000) or record.get("event_type", ""),
            official_severity=None,
            attributes={
                "event_type": record.get("event_type"),
                "sub_event_type": record.get("sub_event_type"),
                "actors": [record.get("actor1"), record.get("actor2")],
                "fatalities": record.get("fatalities"),
                "geo_precision": record.get("geo_precision"),
                "source": record.get("source"),
            },
            source="ACLED",
            publisher="ACLED",
            published_at=to_utc_iso(parse_timestamp(event_date)),
            description=clean_text(record.get("notes"), 1000),
            language="en",
            url=record.get("source") or "https://acleddata.com/",
            is_structured=True,
        )
