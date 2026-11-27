"""Bounded, SSRF-aware HTTP helpers shared by all providers.

Providers only ever fetch *their own* configured endpoints, but the same client
settings (timeouts, user agent, size limits) are reused so a slow or oversized
upstream cannot exhaust the ingestion cycle.
"""

from __future__ import annotations

import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

USER_AGENT = "GlobalEventIntelligence/1.0 (+https://github.com/Rash499/global_event_intelligence)"


def async_client(**overrides) -> httpx.AsyncClient:
    options = {
        "timeout": httpx.Timeout(
            settings.external_request_timeout_seconds,
            connect=min(10.0, settings.external_request_timeout_seconds),
        ),
        "follow_redirects": True,
        "max_redirects": 5,
        "headers": {"User-Agent": USER_AGENT, "Accept": "*/*"},
    }
    options.update(overrides)
    return httpx.AsyncClient(**options)


def bounded_text(response: httpx.Response, limit: int = 4_000_000) -> str:
    content = response.content or b""
    if len(content) > limit:
        logger.warning(
            "Truncating %s response from %s to %s bytes",
            len(content), response.url, limit,
        )
        content = content[:limit]
    return content.decode(response.encoding or "utf-8", errors="replace")
