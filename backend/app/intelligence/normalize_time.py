"""Timestamp helpers shared by the intelligence modules.

Kept in one place so severity, confidence, priority, clustering and the API all
parse provider timestamps identically (always to timezone-aware UTC).
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    iso = text.replace("Z", "+00:00")
    for candidate in (iso, iso.replace(" ", "T", 1)):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def to_utc_iso(value: datetime | str | None) -> str | None:
    parsed = parse_timestamp(value) if not isinstance(value, datetime) else value
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
