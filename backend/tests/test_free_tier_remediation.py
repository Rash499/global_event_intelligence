"""Free-tier audit remediation tests (no network).

Covers: ReliefWeb v2 migration, GDELT 5s pacing + 429 backoff, offline-first
embedding defaults with Ollama fallback, ACLED unverified marking.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import Settings
from app.ingestion.providers import news as news_module
from app.ingestion.providers import structured as structured_module
from app.ingestion.providers.news import GdeltProvider, _retry_after_seconds
from app.ingestion.providers.structured import AcledProvider, ReliefWebProvider
from app.rag.embeddings import HashingEmbeddingProvider, build_embedding_provider


# --- ReliefWeb v2 -------------------------------------------------------

def test_reliefweb_defaults_to_v2():
    settings = Settings()
    assert settings.reliefweb_base_url == "https://api.reliefweb.int/v2"


def test_reliefweb_requires_preapproved_appname_and_v2():
    provider = ReliefWebProvider(Settings(reliefweb_enabled=True, reliefweb_appname=""))
    satisfied, note = provider.validate_config()
    assert not satisfied
    assert "pre-approved" in note

    provider_v1 = ReliefWebProvider(
        Settings(
            reliefweb_enabled=True,
            reliefweb_appname="approved-app-123",
            reliefweb_base_url="https://api.reliefweb.int/v1",
        )
    )
    satisfied, note = provider_v1.validate_config()
    assert not satisfied
    assert "v2" in note


def test_reliefweb_fetch_uses_v2_url_and_appname_only_in_url(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": []}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(structured_module, "async_client", lambda **kw: FakeClient())
    provider = ReliefWebProvider(
        Settings(reliefweb_enabled=True, reliefweb_appname="approved app 1")
    )
    assert asyncio.run(provider.fetch_raw()) == []
    assert captured["url"].startswith("https://api.reliefweb.int/v2/reports?appname=")
    assert "approved%20app%201" in captured["url"]
    assert "appname" not in captured["json"]


# --- GDELT pacing --------------------------------------------------------

def test_gdelt_pacing_waits_full_interval_after_request():
    provider = GdeltProvider(Settings(gdelt_request_interval_seconds=5.0))
    assert provider._seconds_until_next_request(now=100.0) == 0.0
    provider._last_request_at = 100.0
    assert provider._seconds_until_next_request(now=102.0) == 3.0
    assert provider._seconds_until_next_request(now=106.0) == 0.0


def test_retry_after_parsing():
    response = httpx.Response(429, headers={"Retry-After": "17"})
    assert _retry_after_seconds(response, 5.0) == 17.0
    assert _retry_after_seconds(httpx.Response(429), 5.0) == 5.0
    bad = httpx.Response(429, headers={"Retry-After": "soon"})
    assert _retry_after_seconds(bad, 5.0) == 5.0


def test_gdelt_profile_retries_after_429_with_backoff(monkeypatch):
    provider = GdeltProvider(
        Settings(
            gdelt_request_interval_seconds=0.0,
            gdelt_throttle_max_retries=2,
        )
    )
    calls = {"count": 0}
    sleeps: list[float] = []

    class FakeClient:
        async def get(self, url, params=None):
            calls["count"] += 1
            request = httpx.Request("GET", "https://api.gdeltproject.org/api/v2/doc/doc")
            if calls["count"] < 3:
                return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
            return httpx.Response(200, json={"articles": []}, request=request)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(news_module.asyncio, "sleep", fake_sleep)
    payload = asyncio.run(provider._get_profile(FakeClient(), {"query": "test"}))
    assert payload == {"articles": []}
    assert calls["count"] == 3


# --- Embeddings: offline-first -------------------------------------------

def test_embedding_default_is_hashing():
    assert Settings().rag_embedding_provider == "hashing"
    provider = build_embedding_provider(Settings())
    assert isinstance(provider, HashingEmbeddingProvider)


def test_ollama_embedding_falls_back_to_hashing_when_unreachable():
    provider = build_embedding_provider(
        Settings(rag_embedding_provider="ollama", ollama_url="http://127.0.0.1:9")
    )
    assert isinstance(provider, HashingEmbeddingProvider)


# --- ACLED verification marking -------------------------------------------

def test_acled_marked_unverified():
    provider = AcledProvider(Settings())
    assert provider.verification_status == "unverified"
    assert provider.health().as_dict()["verification_status"] == "unverified"


# --- Geocoding config removal ----------------------------------------------

def test_geocoding_settings_removed():
    assert not hasattr(Settings(), "geocoding_provider")
    assert not hasattr(Settings(), "geocoding_base_url")


# --- Weather licence note ----------------------------------------------------

def test_weather_health_declares_licence(db_path):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        payload = client.get("/api/weather/health").json()
    assert "non-commercial" in payload["licence_note"]
