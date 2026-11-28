"""News feed providers: RSS, GDELT and Google News.

These replace the previous one-function collectors.  Behaviour is preserved —
same endpoints, same record shape — but each source is now an adapter with
configuration validation, retries, per-feed health and explicit error reporting
instead of ``except Exception: continue``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import httpx

from ..http import async_client, bounded_text
from ..normalize import clean_text, parse_timestamp, to_utc_iso
from .base import SourceProvider

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# RSS
# ----------------------------------------------------------------------
FEED_REGISTRY: dict[str, dict] = {
    "BBC World": {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "publisher": "BBC", "language": "en"},
    "NPR World": {"url": "https://feeds.npr.org/1004/rss.xml", "publisher": "NPR", "language": "en"},
    "Al Jazeera": {"url": "https://www.aljazeera.com/xml/rss/all.xml", "publisher": "Al Jazeera", "language": "en"},
    "DW World": {"url": "https://rss.dw.com/rdf/rss-en-all", "publisher": "DW", "language": "en"},
    "France 24": {"url": "https://www.france24.com/en/rss", "publisher": "France 24", "language": "en"},
    "NHK World": {"url": "https://www3.nhk.or.jp/rss/news/cat0.xml", "publisher": "NHK World", "language": "en"},
    "Guardian World": {"url": "https://www.theguardian.com/world/rss", "publisher": "The Guardian", "language": "en"},
    "UN News": {"url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "publisher": "UN News", "language": "en"},
    "ReliefWeb Updates": {"url": "https://reliefweb.int/updates/rss.xml", "publisher": "ReliefWeb", "language": "en"},
}

# Backwards-compatible export used by older imports/tests.
DEFAULT_FEEDS = {name: entry["url"] for name, entry in FEED_REGISTRY.items()}


def _entry_image(entry) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        items = entry.get(key) or []
        if items and isinstance(items, list):
            url = items[0].get("url")
            if url:
                return url
    for item in entry.get("enclosures", []) or []:
        if str(item.get("type", "")).startswith("image/"):
            return item.get("href")
    return None


class RssProvider(SourceProvider):
    key = "rss"
    name = "RSS news feeds"
    provider_type = "news"
    default_interval_seconds = 900

    def __init__(self, config=None, feeds: dict[str, dict] | None = None) -> None:
        super().__init__(config)
        if feeds is not None:
            self.feeds = feeds
        elif self.config.rss_include_state_affiliated:
            self.feeds = FEED_REGISTRY
        else:
            state_affiliated = {"Al Jazeera", "DW World", "France 24", "NHK World"}
            self.feeds = {name: spec for name, spec in FEED_REGISTRY.items() if name not in state_affiliated}
        self.feed_status: dict[str, dict] = {}

    async def fetch_raw(self) -> list[dict]:
        max_entries = max(1, self.config.rss_max_entries_per_feed)
        results: list[dict] = []
        errors: list[str] = []

        async with async_client() as client:
            semaphore = asyncio.Semaphore(4)

            async def fetch_feed(name: str, spec: dict) -> list[dict]:
                async with semaphore:
                    started = datetime.now(timezone.utc)
                    try:
                        response = await client.get(spec["url"])
                        response.raise_for_status()
                        parsed = feedparser.parse(bounded_text(response))
                        if getattr(parsed, "bozo", 0) and not parsed.entries:
                            raise ValueError(str(getattr(parsed, "bozo_exception", "malformed feed")))
                        records = []
                        for entry in parsed.entries[:max_entries]:
                            link = entry.get("link")
                            if not link:
                                continue
                            published = (
                                to_utc_iso(parse_timestamp(entry.get("published")))
                                or to_utc_iso(parse_timestamp(entry.get("updated")))
                            )
                            records.append(
                                {
                                    "title": clean_text(entry.get("title"), 400) or "Untitled",
                                    "url": link,
                                    "source": spec.get("publisher") or name,
                                    "publisher": spec.get("publisher") or name,
                                    "published_at": published,
                                    "description": clean_text(entry.get("summary"), 4000),
                                    "image_url": _entry_image(entry),
                                    "author": clean_text(entry.get("author"), 200) or None,
                                    "language": spec.get("language"),
                                    "raw_metadata": {"feed": name},
                                }
                            )
                        self.feed_status[name] = {
                            "status": "healthy",
                            "last_success_at": to_utc_iso(datetime.now(timezone.utc)),
                            "records": len(records),
                            "duration_ms": round(
                                (datetime.now(timezone.utc) - started).total_seconds() * 1000, 2
                            ),
                            "url": spec["url"],
                            "error": None,
                        }
                        return records
                    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                        message = f"{type(exc).__name__}: {exc}"
                        self.feed_status[name] = {
                            "status": "unavailable",
                            "last_success_at": self.feed_status.get(name, {}).get("last_success_at"),
                            "records": 0,
                            "duration_ms": round(
                                (datetime.now(timezone.utc) - started).total_seconds() * 1000, 2
                            ),
                            "url": spec["url"],
                            "error": message,
                        }
                        errors.append(f"{name}: {message}")
                        logger.warning("[RSS] feed %s failed: %s", name, message)
                        return []

            batches = await asyncio.gather(
                *(fetch_feed(name, spec) for name, spec in self.feeds.items())
            )
            for batch in batches:
                results.extend(batch)

        if errors and len(errors) == len(self.feeds):
            # Every feed failed: surface it as a provider failure.
            raise RuntimeError("; ".join(errors[:3]))

        self.errors = errors
        return results

    def health(self, stored=None):
        health = super().health(stored)
        failures = [
            name for name, status in self.feed_status.items() if status["status"] != "healthy"
        ]
        if failures and health.status == "healthy":
            health.status = "degraded"
            health.notes = f"{len(failures)} of {len(self.feed_status)} feeds unavailable."
        return health


# ----------------------------------------------------------------------
# GDELT
# ----------------------------------------------------------------------
# Query profiles replace the single narrow ``sourcelang:english`` query, so
# coverage is not limited to English-language general news.
GDELT_QUERY_PROFILES: dict[str, str] = {
    "conflict": '(conflict OR war OR military OR airstrike OR "armed clash" OR ceasefire)',
    "disaster": '(earthquake OR flood OR wildfire OR cyclone OR hurricane OR tsunami OR landslide OR volcano)',
    "politics": '(election OR protest OR sanctions OR coup OR parliament OR "state of emergency")',
    "health": '(outbreak OR epidemic OR pandemic OR humanitarian OR famine OR refugees)',
    "economy": '(inflation OR recession OR "central bank" OR default OR "supply chain")',
    "security": '(terror OR "cyber attack" OR ransomware OR "border incident")',
}


def _retry_after_seconds(response, fallback: float) -> float:
    """Parse a ``Retry-After`` header (seconds form); fall back if absent."""
    raw = response.headers.get("Retry-After") if response is not None else None
    try:
        return max(0.0, float(raw)) if raw else fallback
    except (TypeError, ValueError):
        return fallback


class GdeltProvider(SourceProvider):
    key = "gdelt"
    name = "GDELT Global Knowledge Graph"
    provider_type = "news"
    docs_url = "https://www.gdeltproject.org/"
    default_interval_seconds = 1800

    API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, config=None) -> None:
        super().__init__(config)
        # Monotonic timestamp of the last GDELT request. Providers are
        # process-wide singletons, so this paces requests across query
        # profiles *and* across the base collector's retries of fetch_raw.
        self._last_request_at: float | None = None

    def _seconds_until_next_request(self, now: float) -> float:
        """How long to wait before the next request is within the pacing rule."""
        interval = max(0.0, float(self.config.gdelt_request_interval_seconds))
        if self._last_request_at is None or interval <= 0:
            return 0.0
        return max(0.0, interval - (now - self._last_request_at))

    async def _pace(self) -> None:
        """Sleep until the next GDELT request respects the 1-per-5s rule."""
        import time as _time

        wait = self._seconds_until_next_request(_time.monotonic())
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_at = _time.monotonic()

    async def _get_profile(self, client, params: dict) -> dict:
        """GET one query profile, honouring HTTP 429 backoff.

        GDELT throttles with 429 (often plain text, not JSON). We wait for
        ``Retry-After`` when supplied, otherwise exponential backoff from the
        pacing interval, and retry the profile a bounded number of times
        instead of failing it immediately or hammering the endpoint.
        """
        import time as _time

        interval = max(0.0, float(self.config.gdelt_request_interval_seconds))
        max_throttle_retries = max(0, int(self.config.gdelt_throttle_max_retries))
        for throttle_attempt in range(max_throttle_retries + 1):
            await self._pace()
            response = await client.get(self.API_URL, params=params)
            if response.status_code != 429:
                response.raise_for_status()
                return response.json()
            self._last_request_at = _time.monotonic()
            if throttle_attempt >= max_throttle_retries:
                response.raise_for_status()  # raises HTTPStatusError (429)
            wait = _retry_after_seconds(
                response, interval * (2**throttle_attempt) if interval else 5.0
            )
            logger.warning(
                "[GDELT] throttled (429); backing off %.1fs (retry %s/%s)",
                wait, throttle_attempt + 1, max_throttle_retries,
            )
            if wait > 0:
                await asyncio.sleep(wait)
        return {}  # pragma: no cover - loop always returns or raises

    async def fetch_raw(self) -> list[dict]:
        max_records = max(1, min(250, self.config.gdelt_max_records))
        languages = self.config.gdelt_language_list or ["english"]
        per_profile = max(10, max_records // max(len(GDELT_QUERY_PROFILES), 1))
        results: list[dict] = []
        errors: list[str] = []

        lang_clause = (
            f"sourcelang:{languages[0]}"
            if len(languages) == 1
            else "(" + " OR ".join(f"sourcelang:{lang}" for lang in languages) + ")"
        )
        start = datetime.now(timezone.utc) - timedelta(
            hours=max(1, self.config.gdelt_time_window_hours)
        )

        async with async_client() as client:
            for profile, query in GDELT_QUERY_PROFILES.items():
                params = {
                    "query": f"{lang_clause} {query}",
                    "mode": "artlist",
                    "format": "json",
                    "maxrecords": per_profile,
                    "sort": "datedesc",
                    "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                }
                try:
                    payload = await self._get_profile(client, params)
                except (httpx.HTTPError, ValueError) as exc:
                    message = f"{profile}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    logger.warning("[GDELT] profile %s failed: %s", profile, message)
                    continue

                for item in payload.get("articles", []) or []:
                    url = item.get("url")
                    if not url:
                        continue
                    results.append(
                        {
                            "title": clean_text(item.get("title"), 400) or "Untitled",
                            "url": url,
                            "source": item.get("domain") or "GDELT",
                            "publisher": item.get("domain"),
                            "published_at": to_utc_iso(parse_timestamp(item.get("seendate"))),
                            "description": clean_text(item.get("title"), 400),
                            "image_url": item.get("socialimage"),
                            "language": item.get("language"),
                            "raw_metadata": {
                                "profile": profile,
                                "sourcecountry": item.get("sourcecountry"),
                                "domain": item.get("domain"),
                            },
                        }
                    )

        if errors and len(errors) == len(GDELT_QUERY_PROFILES):
            raise RuntimeError("; ".join(errors[:3]))

        self.errors = errors
        return results

    def health(self, stored=None):
        health = super().health(stored)
        if getattr(self, "errors", None) and health.status == "healthy":
            health.status = "degraded"
            health.notes = f"{len(self.errors)} GDELT query profile(s) failed this cycle."
        return health


# ----------------------------------------------------------------------
# Google News
# ----------------------------------------------------------------------
GOOGLE_NEWS_QUERIES = {
    "Global": "world news",
    "Conflicts": "war OR conflict OR ceasefire",
    "Disasters": "earthquake OR flood OR wildfire OR hurricane",
    "Economy": "economy OR inflation OR recession",
    "Technology": "technology OR artificial intelligence",
    "Science": "science OR space OR climate",
    "Health": "health OR disease OR pandemic",
}

GOOGLE_NEWS_URL = "https://news.google.com/rss/search"


class GoogleNewsProvider(SourceProvider):
    key = "google_news"
    name = "Google News RSS"
    provider_type = "news"
    docs_url = "https://news.google.com/"
    default_interval_seconds = 1800

    async def fetch_raw(self) -> list[dict]:
        per_query = max(1, self.config.google_news_max_per_query)
        hl = self.config.google_news_language
        gl = self.config.google_news_country
        ceid = f"{gl}:{hl.split('-')[0]}"
        results: list[dict] = []
        errors: list[str] = []

        async with async_client() as client:
            for label, query in GOOGLE_NEWS_QUERIES.items():
                try:
                    response = await client.get(
                        GOOGLE_NEWS_URL,
                        params={"q": query, "hl": hl, "gl": gl, "ceid": ceid},
                    )
                    response.raise_for_status()
                    feed = feedparser.parse(bounded_text(response))
                except (httpx.HTTPError, ValueError) as exc:
                    message = f"{label}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    logger.warning("[GOOGLE NEWS] query %s failed: %s", label, message)
                    continue

                for entry in feed.entries[:per_query]:
                    link = entry.get("link")
                    if not link:
                        continue
                    source = entry.get("source")
                    publisher = source.get("title") if isinstance(source, dict) else None
                    results.append(
                        {
                            "title": clean_text(entry.get("title"), 400) or "Untitled",
                            "url": link,
                            "source": f"Google News: {publisher or label}",
                            "publisher": publisher,
                            "published_at": to_utc_iso(parse_timestamp(entry.get("published"))),
                            "description": clean_text(entry.get("summary"), 4000),
                            "image_url": None,
                            "raw_metadata": {"query": label, "publisher": publisher},
                        }
                    )

        if errors and len(errors) == len(GOOGLE_NEWS_QUERIES):
            raise RuntimeError("; ".join(errors[:3]))

        self.errors = errors
        return results

    def health(self, stored=None):
        health = super().health(stored)
        if getattr(self, "errors", None) and health.status == "healthy":
            health.status = "degraded"
            health.notes = f"{len(self.errors)} Google News query group(s) failed this cycle."
        return health
