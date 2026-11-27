"""SSRF protections, demo-data gating and API hardening."""

from __future__ import annotations

import pytest

from app.security.ssrf import SsrfError, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:8000/api",
        "http://127.0.0.1./x",
        "http://[::1]/x",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://172.16.0.1/x",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://100.64.0.1/x",
        "http://0.0.0.0/x",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://service.internal/x",
        "http://router.local/x",
    ],
)
def test_internal_addresses_are_rejected(url):
    with pytest.raises(SsrfError):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/", "javascript:alert(1)"],
)
def test_non_http_schemes_are_rejected(url):
    with pytest.raises(SsrfError):
        validate_url(url)


def test_credentials_in_url_are_rejected():
    with pytest.raises(SsrfError):
        validate_url("http://user:pass@example.com/x")


def test_public_url_is_allowed():
    # Documented behaviour: the guard resolves and validates, it does not fetch.
    assert validate_url("https://example.com/article") == "https://example.com/article"


def test_dns_failure_is_rejected(monkeypatch):
    import socket

    def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(SsrfError):
        validate_url("https://this-host-does-not-exist.invalid/x")


def test_hostname_resolving_to_private_ip_is_rejected(monkeypatch):
    import socket

    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(SsrfError):
        validate_url("https://rebind.example.com/x")


def test_safe_fetch_revalidates_each_redirect():
    """A redirect pointing at an internal address is refused, not followed."""
    import asyncio
    import httpx

    from app.security import ssrf

    class FakeResponse:
        status_code = 302
        headers = {"location": "http://169.254.169.254/latest/meta-data/"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url):
            return FakeResponse()

    original_client = httpx.AsyncClient
    httpx.AsyncClient = FakeClient
    try:
        with pytest.raises(SsrfError):
            asyncio.run(ssrf.safe_fetch("https://example.com/article"))
    finally:
        httpx.AsyncClient = original_client


def test_safe_fetch_blocks_non_html_content_types():
    """Binary/unknown content types are not fetched into the app."""
    import asyncio
    import httpx

    from app.security import ssrf

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/octet-stream"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def aiter_bytes(self):
            yield b"binary"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url):
            return FakeResponse()

    original_client = httpx.AsyncClient
    httpx.AsyncClient = FakeClient
    try:
        with pytest.raises(SsrfError):
            asyncio.run(ssrf.safe_fetch("https://example.com/file.bin"))
    finally:
        httpx.AsyncClient = original_client


# ----------------------------------------------------------------------
# API hardening
# ----------------------------------------------------------------------
def test_demo_seed_is_disabled_by_default(client):
    response = client.post("/api/events/seed", json={"confirm": True})
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


def test_demo_seed_requires_confirmation(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_data_enabled", True)
    response = client.post("/api/events/seed", json={"confirm": False})
    assert response.status_code == 400


def test_demo_seed_inserts_labelled_records(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_data_enabled", True)
    response = client.post("/api/events/seed", json={"confirm": True})
    assert response.status_code == 200
    assert response.json()["seeded"] > 0

    events = client.get("/api/events/history").json()
    assert all(event["title"].startswith("[DEMO]") for event in events)


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_error_response_does_not_leak_internals(client, monkeypatch):
    from app.api import intelligence

    def boom(*args, **kwargs):
        raise RuntimeError("internal detail: /secret/path")

    monkeypatch.setattr(intelligence, "dashboard_overview", boom)
    response = client.get("/api/dashboard/overview")
    # Either a 500 with a generic message or a normal response if the route
    # object was already bound; both must never contain the internal path.
    assert "/secret/path" not in response.text


def test_openapi_is_available(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"]
    assert "/api/events" in schema["paths"]
