"""Lightweight in-process scheduler.

Deliberately not a distributed queue: the platform runs as a single FastAPI
process against SQLite, and that is the requirement it must satisfy.

Properties:

* each provider is scheduled **independently** at its configured interval, with
  a small initial jitter so all providers do not fire in the same second;
* a provider job never overlaps itself;
* one provider failing (or timing out) does not affect the others;
* the loop is cancellable and shuts down promptly;
* the last/next run times are persisted through the normal collection-run and
  provider-health tables, so the UI reflects real history.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..ingestion.registry import PROVIDERS, provider_interval_seconds, record_run

logger = logging.getLogger(__name__)

_running: set[str] = set()
_next_run: dict[str, datetime] = {}
_last_run: dict[str, str] = {}


def schedule_state() -> dict:
    return {
        "enabled": settings.scheduler_enabled,
        "tick_seconds": settings.scheduler_tick_seconds,
        "running": sorted(_running),
        "jobs": [
            {
                "provider": key,
                "interval_seconds": provider_interval_seconds(key),
                "next_run_at": _next_run.get(key).isoformat() if key in _next_run else None,
                "last_run_at": _last_run.get(key),
                "enabled": provider.is_enabled() and provider.validate_config()[0],
            }
            for key, provider in PROVIDERS.items()
        ],
    }


async def _run_job(key: str) -> None:
    if key in _running:
        logger.debug("[SCHEDULER] %s still running; skipping this tick", key)
        return
    provider = PROVIDERS.get(key)
    if provider is None or not provider.is_enabled() or not provider.validate_config()[0]:
        return

    _running.add(key)
    try:
        logger.info("[SCHEDULER] collecting %s", key)
        result = await provider.collect(trigger="scheduled")
        record_run(result, trigger="scheduled")
        _last_run[key] = datetime.now(timezone.utc).isoformat()
        # A provider that hit its circuit breaker backs off further.
        multiplier = 3 if result.status == "unavailable" else 1
        _next_run[key] = datetime.now(timezone.utc) + timedelta(
            seconds=provider_interval_seconds(key) * multiplier
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("[SCHEDULER] provider %s failed", key)
        _next_run[key] = datetime.now(timezone.utc) + timedelta(
            seconds=provider_interval_seconds(key)
        )
    finally:
        _running.discard(key)


async def scheduler_loop() -> None:
    """Main scheduling loop. Runs until cancelled."""
    now = datetime.now(timezone.utc)
    for index, key in enumerate(PROVIDERS):
        # Spread the first runs over the first couple of minutes.
        _next_run[key] = now + timedelta(seconds=5 + (index * 4) + random.uniform(0, 3))

    tick = max(5, settings.scheduler_tick_seconds)
    logger.info("[SCHEDULER] started with a %ss tick", tick)

    while True:
        try:
            now = datetime.now(timezone.utc)
            due = [key for key, when in _next_run.items() if when <= now]
            for key in due:
                # Fire and forget: independent jobs, never awaited in sequence.
                asyncio.create_task(_run_job(key))
                _next_run[key] = now + timedelta(seconds=provider_interval_seconds(key))
            await asyncio.sleep(tick)
        except asyncio.CancelledError:
            logger.info("[SCHEDULER] stopping")
            raise
        except Exception:
            logger.exception("[SCHEDULER] tick failed; continuing")
            await asyncio.sleep(tick)
