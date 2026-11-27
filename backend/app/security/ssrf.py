"""SSRF-safe fetching of externally supplied URLs.

The image discovery feature fetched article URLs (untrusted input) with
``follow_redirects=True`` and no validation, so a crafted article URL could make
the backend request internal services.  This module is the only way the
application may fetch a URL that came from article content.

Protections:

* only ``http``/``https`` schemes;
* hostname resolved first and every resolved address checked against private,
  loopback, link-local, multicast, reserved and unspecified ranges;
* redirects are followed **manually**, and each hop is re-validated (this is
  what prevents DNS-rebinding style bypasses where the first hop is public);
* a hard redirect limit, timeout, response size cap and content-type check;
* errors returned to callers are generic — internal addresses and DNS details
  are never echoed to the client or written into API responses.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
BLOCKED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata", "metadata.google.internal", "instance-data",
    "kubernetes.default", "kubernetes.default.svc",
}


class SsrfError(Exception):
    """Raised when a URL must not be fetched. Message is safe to log."""


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str
    final_url: str


# Networks that must never be reached. ``ipaddress`` flags most of these, but
# CGNAT (RFC 6598) and the benchmark/documentation ranges are not reported as
# private, and they are exactly the kind of range reachable inside cloud VPCs.
BLOCKED_NETWORKS = [
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
        "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
        "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
        "::1/128", "::/128", "fc00::/7", "fe80::/10", "ff00::/8",
        "64:ff9b::/96", "2001:db8::/32",
    )
]


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    if settings.ssrf_allow_private_hosts:
        return False
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return True
    if ip.is_reserved or ip.is_unspecified or getattr(ip, "is_site_local", False):
        return True
    # A v4-mapped v6 address must be judged by the v4 rules it embeds.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _is_blocked_ip(str(mapped))
    return any(ip in network for network in BLOCKED_NETWORKS if network.version == ip.version)


def validate_url(url: str, allow_private: bool | None = None) -> str:
    """Validate scheme/host and resolve DNS, rejecting internal targets.

    Returns the normalised URL. Raises :class:`SsrfError` otherwise.
    """
    if not url or not isinstance(url, str):
        raise SsrfError("Empty URL")

    try:
        parsed = urlparse(url.strip())
    except ValueError as exc:
        raise SsrfError("Malformed URL") from exc

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SsrfError("Only http and https URLs may be fetched")
    if not parsed.hostname:
        raise SsrfError("URL has no hostname")
    if parsed.username or parsed.password:
        raise SsrfError("URLs with embedded credentials are rejected")

    hostname = parsed.hostname.lower().strip(".")
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise SsrfError("Target host is not permitted")

    # A literal IP is checked directly; a hostname must resolve to safe addresses.
    try:
        literal = ipaddress.ip_address(hostname)
        if not (allow_private or settings.ssrf_allow_private_hosts) and _is_blocked_ip(str(literal)):
            raise SsrfError("Target address is not permitted")
        return url.strip()
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise SsrfError("Hostname could not be resolved") from exc

    addresses = {info[4][0] for info in infos if info[4]}
    if not addresses:
        raise SsrfError("Hostname could not be resolved")
    if not (allow_private or settings.ssrf_allow_private_hosts):
        for address in addresses:
            if _is_blocked_ip(address):
                raise SsrfError("Target resolves to a non-public address")
    return url.strip()


def _check_content_type(content_type: str) -> None:
    main = (content_type or "").split(";")[0].strip().lower()
    if main and main not in ALLOWED_CONTENT_TYPES:
        raise SsrfError(f"Unsupported content type: {main}")


async def safe_fetch(
    url: str,
    *,
    max_bytes: int | None = None,
    timeout: float | None = None,
    allowed_content_types: set[str] | None = None,
) -> FetchResult:
    """Fetch a URL with redirect-by-redirect validation and size limits."""
    max_bytes = max_bytes or settings.ssrf_max_response_bytes
    timeout = timeout or settings.ssrf_timeout_seconds
    allowed = allowed_content_types or ALLOWED_CONTENT_TYPES
    max_redirects = max(0, settings.ssrf_max_redirects)

    current = validate_url(url)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": "GlobalEventIntelligence/1.0"},
    ) as client:
        for hop in range(max_redirects + 1):
            try:
                async with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or hop >= max_redirects:
                            raise SsrfError("Too many redirects")
                        current = validate_url(urljoin(current, location))
                        continue

                    if response.status_code >= 400:
                        raise SsrfError(f"Upstream responded with status {response.status_code}")

                    content_type = response.headers.get("content-type", "")
                    main = content_type.split(";")[0].strip().lower()
                    if main and main not in allowed:
                        raise SsrfError("Unsupported content type")

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            break
                        chunks.append(chunk)

                    return FetchResult(
                        url=url,
                        status_code=response.status_code,
                        content_type=main or "unknown",
                        text=b"".join(chunks).decode("utf-8", errors="replace"),
                        final_url=str(response.url),
                    )
            except httpx.HTTPError as exc:
                raise SsrfError(f"Request failed: {type(exc).__name__}") from exc

    raise SsrfError("Too many redirects")
