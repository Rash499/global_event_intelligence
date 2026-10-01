"""Ollama chat client for grounded answer generation.

Uses the local Ollama HTTP API directly (``/api/chat``) with short, explicit
timeouts so the assistant degrades gracefully: every function here either
returns usable data or raises :class:`LLMError`, which the service layer turns
into a structured "llm_unavailable" answer. Nothing else in the platform
depends on Ollama being reachable.
"""

import asyncio
import logging
import time

import httpx

from ..config import Settings, settings as global_settings
from .vector_store import tcp_reachable

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120.0
AVAILABILITY_TIMEOUT = 2.0


class LLMError(RuntimeError):
    """Raised when the chat model cannot produce an answer."""


def _root(config: Settings) -> str:
    return config.ollama_root


async def list_models(config: Settings | None = None, timeout: float | None = None) -> list[str]:
    """Return the names of the models installed on the Ollama server."""
    config = config or global_settings

    # Fail fast when nothing is listening: waiting for the HTTP connect timeout
    # (once per resolved address) is what made a stopped Ollama feel like a
    # frozen backend. The check costs ~0.2s in the worst case and ~0ms when the
    # connection is refused immediately.
    if not await asyncio.to_thread(tcp_reachable, config.ollama_url, 0.2):
        raise LLMError(f"Ollama is not reachable at {config.ollama_url}")

    try:
        async with httpx.AsyncClient(
            timeout=timeout or config.ollama_availability_timeout_seconds
        ) as client:
            response = await client.get(f"{_root(config)}/api/tags")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMError(f"Ollama is not reachable at {config.ollama_url}: {exc}") from exc

    names: list[str] = []
    for model in payload.get("models") or []:
        name = model.get("name") or model.get("model")
        if name:
            names.append(str(name))
    return names


_AVAILABILITY_CACHE: dict[str, tuple[float, bool, str | None]] = {}


async def is_available(config: Settings | None = None) -> tuple[bool, str | None]:
    """Check that Ollama answers and the configured chat model exists.

    Returns ``(available, detail)``; ``detail`` explains the failure when the
    model is missing (the server itself responding is not enough).

    The result is cached for ``rag_llm_availability_cache_ttl_seconds``. This
    probe costs hundreds of milliseconds against a loaded model server and is
    called by the polled status endpoint; a few seconds of staleness is fine,
    because a model that disappears is still caught by :func:`chat`.
    """
    config = config or global_settings
    ttl = max(0.0, float(config.rag_llm_availability_cache_ttl_seconds))
    key = f"{config.ollama_root}|{config.chat_model}"

    if ttl > 0:
        cached = _AVAILABILITY_CACHE.get(key)
        if cached is not None and (time.monotonic() - cached[0]) < ttl:
            return cached[1], cached[2]

    available, detail = await _probe_availability(config)

    if ttl > 0:
        _AVAILABILITY_CACHE[key] = (time.monotonic(), available, detail)

    return available, detail


async def _probe_availability(config: Settings) -> tuple[bool, str | None]:
    try:
        names = await list_models(config)
    except LLMError as exc:
        return False, str(exc)

    wanted = config.chat_model
    if wanted in names:
        return True, None

    base = wanted.split(":")[0]
    if any(name.split(":")[0] == base for name in names):
        return True, None

    return False, (
        f"Chat model '{wanted}' is not installed on the Ollama server "
        f"(available: {', '.join(names) or 'none'}). "
        f"Run: ollama pull {wanted}"
    )


def reset_availability_cache() -> None:
    """Forget cached availability probes (used by tests)."""
    _AVAILABILITY_CACHE.clear()


async def chat(
    system_prompt: str,
    user_prompt: str,
    config: Settings | None = None,
) -> str:
    """Generate the grounded answer text for one question.

    Raises :class:`LLMError` for connectivity, HTTP and payload problems so
    callers never see raw ``httpx`` exceptions.
    """
    config = config or global_settings

    options = {
        "temperature": float(config.ollama_temperature),
        "num_ctx": int(config.ollama_num_ctx),
    }
    # Bound generation: an uncapped small model writes until it decides it is
    # finished, which is what made answers take 20+ seconds.
    if config.ollama_max_tokens and config.ollama_max_tokens > 0:
        options["num_predict"] = int(config.ollama_max_tokens)

    payload = {
        "model": config.chat_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": options,
    }

    try:
        async with httpx.AsyncClient(timeout=config.ollama_request_timeout_seconds) as client:
            response = await client.post(f"{_root(config)}/api/chat", json=payload)
    except httpx.TimeoutException as exc:
        raise LLMError(
            f"The local AI model did not respond within "
            f"{config.ollama_request_timeout_seconds:.0f}s."
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama is not reachable at {config.ollama_url}: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:300].replace("\n", " ")
        raise LLMError(f"Ollama chat request failed ({response.status_code}): {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError("Ollama returned a non-JSON chat response") from exc

    content = ((data.get("message") or {}).get("content")) or ""
    if not str(content).strip():
        raise LLMError("Ollama returned an empty answer")

    return str(content)
