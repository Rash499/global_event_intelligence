"""Timestamp helpers for the RAG layer.

The platform stores timestamps in several formats because the ingestion
pipeline copies whatever the upstream source provides:

* ISO-8601 (``2026-09-28T16:30:00+00:00``)
* SQLite ``CURRENT_TIMESTAMP`` (``2026-09-28 16:57:29``)
* GDELT compact (``20260928T163000Z``)
* RFC-822 publish dates (``Sun, 27 Sep 2026 17:05:26 GMT``)
* plain dates (``2026-09-28``)

Everything the RAG layer needs (filters, timelines, ordering) is derived from
:func:`to_epoch` and :func:`to_iso`, so mixed formats behave consistently.
"""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y%m%dT%H%M%SZ",
    "%Y%m%d%H%M%S",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value) -> datetime | None:
    """Parse any of the timestamp formats used by the platform."""
    if value is None or isinstance(value, datetime):
        return value if isinstance(value, datetime) else None

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z") and "T" in text:
        candidate = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass

    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt in FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass

    return None


def to_epoch(value) -> float | None:
    """Return the UTC epoch seconds for a stored timestamp."""
    parsed = parse_timestamp(value)
    return parsed.timestamp() if parsed else None


def to_iso(value) -> str | None:
    """Normalise a stored timestamp to ISO-8601 (UTC)."""
    parsed = parse_timestamp(value)
    if not parsed:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def days_ago_epoch(days: int) -> float:
    """Epoch seconds for ``days`` ago (used by relative date filters)."""
    return (utc_now() - timedelta(days=max(0, int(days)))).timestamp()


def start_of_day_epoch(days_ago: int = 0) -> float:
    """Epoch seconds for midnight UTC ``days_ago`` days in the past."""
    now = utc_now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - timedelta(days=int(days_ago))).timestamp()
