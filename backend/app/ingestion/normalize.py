"""Normalisation of provider records into the platform article schema.

Every collector returns provider-shaped dictionaries; this module turns them
into one structure the rest of the pipeline can rely on.  Normalisation never
invents data: fields that a provider did not supply stay ``None`` and are
flagged through ``extraction_status``.

Timestamp handling is deliberately explicit.  The platform separates:

``published_at``     when the publisher says the article appeared
``source_record_at`` the provider's own timestamp for the record
``event_time``       when the described incident happened (only when evidenced)
``first_seen_at``    when this platform first observed the record
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone

from ..config import settings
from ..intelligence.urls import (
    canonicalize_url,
    extract_google_news_publisher,
    publisher_domain,
)

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
CASUALTY_RE = re.compile(
    r"\b(?:at least\s+)?(\d{1,7})\s+(?:people\s+)?(?:were\s+)?"
    r"(?:killed|dead|died|injured|wounded|missing)\b",
    re.IGNORECASE,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def parse_timestamp(value) -> datetime | None:
    """Parse the many timestamp shapes the providers emit, always to aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:  # milliseconds
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    # GDELT: 20240115T123000Z
    if re.fullmatch(r"\d{8}T\d{6}Z", text):
        try:
            return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # RFC 822/2822 (RSS)
    from email.utils import parsedate_to_datetime

    try:
        parsed = parsedate_to_datetime(text)
        if parsed:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    iso = text.replace("Z", "+00:00")
    for candidate in (iso, iso.replace(" ", "T", 1)):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def clean_text(value: str | None, limit: int | None = None) -> str:
    """Strip markup/entities/control characters from untrusted provider text."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\x00", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def detect_language(text: str, fallback: str | None = None) -> str:
    """Cheap, dependency-free language hint.

    Only used for display/labels: no behavioural decision depends on it, and it
    never overrides a language the provider supplied.
    """
    if fallback:
        return fallback.strip().lower()[:12]
    sample = (text or "").lower()
    if not sample:
        return "und"
    non_latin = {
        "ar": "\u0600-\u06ff",
        "ru": "\u0400-\u04ff",
        "he": "\u0590-\u05ff",
        "hi": "\u0900-\u097f",
        "ta": "\u0b80-\u0bff",
        "zh": "\u4e00-\u9fff",
        "ja": "\u3040-\u30ff",
        "ko": "\uac00-\ud7af",
        "th": "\u0e00-\u0e7f",
    }
    for code, rng in non_latin.items():
        if re.search(f"[{rng}]", sample):
            return code
    return "en"


def _event_time_from_text(text: str) -> tuple[str | None, str]:
    """Extract an incident time only when the text states one explicitly.

    Returns ``(iso_or_none, precision)``.  Publication time is deliberately not
    used as a fallback: that would claim the incident and the article happened
    at the same moment.
    """
    if not text:
        return None, "unknown"

    lowered = text.lower()
    if re.search(r"\b(?:\d+\s+(?:minutes?|hours?)\s+ago|just now|moments ago)\b", lowered):
        return to_utc_iso(utc_now()), "approximate"

    match = re.search(
        r"\b(?:on\s+)?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)\b",
        text,
    )
    if match:
        parsed = parse_timestamp(match.group(1))
        if parsed:
            return to_utc_iso(parsed), "timestamp"

    match = re.search(
        r"\b(?:on\s+)?(\d{1,2}\s+"
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        parsed = parse_timestamp(match.group(1))
        if parsed:
            return to_utc_iso(parsed), "date"

    return None, "unknown"


def extract_reported_casualties(text: str) -> int | None:
    """Largest headline casualty figure stated in the text, if any."""
    numbers = [int(m.group(1)) for m in CASUALTY_RE.finditer(text or "")]
    meaningful = [n for n in numbers if 0 < n < 1_000_000]
    return max(meaningful) if meaningful else None


def content_hash(title: str, description: str) -> str:
    from ..intelligence.deduplication import normalize_text

    value = f"{normalize_text(title)}|{normalize_text(description)}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_article(raw: dict, provider: str) -> dict | None:
    """Turn a provider record into the platform article structure.

    Returns ``None`` when the record cannot be stored at all (no URL/title),
    which the caller counts as *rejected* rather than silently dropping.
    """
    url = str(raw.get("url") or "").strip()
    title = clean_text(raw.get("title"), limit=400)
    description = clean_text(
        raw.get("description") or raw.get("summary") or "", limit=4000
    )

    if not url or not title:
        return None

    source_label = clean_text(raw.get("source"))
    domain = publisher_domain(url, raw.get("publisher_domain"))
    publisher = clean_text(raw.get("publisher")) or domain or source_label or "Unknown"

    # Google News wraps other publishers: recover the real one.
    reporting_type = "direct"
    if "news.google.com" in domain:
        google_publisher, clean_title = extract_google_news_publisher(title, url)
        publisher = clean_title and google_publisher or publisher
        title = clean_title or title
        reporting_type = "aggregated"

    published = parse_timestamp(raw.get("published_at"))
    source_record = parse_timestamp(raw.get("source_record_at")) or published
    event_time_iso, event_time_precision = _event_time_from_text(
        f"{title}. {description}"
    )
    if raw.get("event_time"):
        explicit = parse_timestamp(raw.get("event_time"))
        if explicit:
            event_time_iso = to_utc_iso(explicit)
            event_time_precision = raw.get("event_time_precision") or "timestamp"

    now_iso = to_utc_iso(utc_now())

    provider_record_id = raw.get("provider_record_id")
    if not provider_record_id:
        provider_record_id = raw.get("external_id") or raw.get("id")

    language = detect_language(f"{title} {description}", raw.get("language"))

    article = {
        "title": title,
        "url": url,
        "canonical_url": canonicalize_url(url),
        "description": description,
        "source": source_label or publisher,
        "publisher": publisher,
        "publisher_domain": domain,
        "provider": provider,
        "provider_record_id": str(provider_record_id) if provider_record_id else None,
        "published_at": to_utc_iso(published),
        "source_record_at": to_utc_iso(source_record),
        "first_seen_at": now_iso,
        "last_seen_at": now_iso,
        "language": language,
        "author": clean_text(raw.get("author"), limit=200) or None,
        "image_url": raw.get("image_url") or None,
        "content_hash": content_hash(title, description),
        "description_hash": hashlib.sha256(
            (description or "").encode("utf-8")
        ).hexdigest(),
        "extraction_status": "metadata",
        "reporting_type": reporting_type,
        "syndication_of": raw.get("syndication_of"),
        "event_time": event_time_iso,
        "event_time_precision": event_time_precision,
        "reported_casualties": extract_reported_casualties(f"{title}. {description}"),
        "raw_metadata": raw.get("raw_metadata"),
        "is_independent": 0 if domain and _is_aggregator(domain) else 1,
    }

    if article["published_at"] is None and article["event_time"] is not None:
        # The provider gave an incident time but no publication time; the
        # publication time stays unknown on purpose.
        article["extraction_status"] = "partial"

    return article


def _is_aggregator(domain: str) -> bool:
    from ..intelligence.urls import is_aggregator

    return is_aggregator(domain, settings.syndication_domain_set)
