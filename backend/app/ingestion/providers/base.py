"""Provider adapter framework.

Every external source implements the same lifecycle so the ingestion service,
the scheduler, the health view and the tests treat them identically:

``identify`` → ``validate_config`` → ``fetch`` → ``normalise`` → ``health``

Guarantees this layer provides (they were missing before):

* per-provider timeouts and bounded retries with exponential backoff;
* a circuit breaker after repeated failures, so a dead provider stops being
  hammered on every cycle;
* failures are **recorded**, never swallowed — one broken provider cannot take
  down the others;
* structured collection results with received/accepted/rejected/duplicate counts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ...config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

HEALTHY = "healthy"
IDLE = "idle"  # enabled and configured, but never collected yet
DEGRADED = "degraded"
UNAVAILABLE = "unavailable"
NOT_CONFIGURED = "not_configured"
DISABLED = "disabled"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProviderRecord:
    """A raw record as returned by a provider, before normalisation."""

    data: dict
    provider: str
    raw: dict | None = None


@dataclass
class CollectionResult:
    provider: str
    status: str
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    duration_ms: float = 0.0
    records_received: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    records_duplicate: int = 0
    records_failed: int = 0
    events_created: int = 0
    events_updated: int = 0
    articles: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    skipped_reason: str | None = None

    def finish(self, status: str | None = None) -> "CollectionResult":
        self.finished_at = utc_now_iso()
        if status:
            self.status = status
        try:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.finished_at)
            self.duration_ms = round((end - start).total_seconds() * 1000, 2)
        except ValueError:
            pass
        return self

    @property
    def ok(self) -> bool:
        return self.status in {HEALTHY, DEGRADED}

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "records_received": self.records_received,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "records_duplicate": self.records_duplicate,
            "records_failed": self.records_failed,
            "events_created": self.events_created,
            "events_updated": self.events_updated,
            "errors": self.errors[:10],
            "details": self.details,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class ProviderHealth:
    provider: str
    name: str
    provider_type: str
    enabled: bool
    config_satisfied: bool
    status: str
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    circuit_open_until: str | None = None
    avg_duration_ms: float | None = None
    notes: str | None = None
    docs_url: str | None = None
    requires_credentials: bool = False
    # "verified" = exercised/tested as documented; "unverified" = implemented
    # against published docs but never run against a real account, so live
    # operation must not be claimed.
    verification_status: str = "verified"

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class SourceProvider:
    """Base class for every data provider.

    Subclasses implement :meth:`fetch_raw` (I/O + parsing) and optionally
    :meth:`normalise` (defaults to the shared article normaliser).
    """

    key: str = "base"
    name: str = "Base provider"
    provider_type: str = "news"
    docs_url: str | None = None
    requires_credentials: bool = False
    verification_status: str = "verified"
    # Structured providers (USGS, CAP…) produce events directly rather than
    # news articles; the ingestion service branches on this flag.
    produces_structured_observations: bool = False
    default_interval_seconds: int = 1800
    # Override these per source when a published schedule is slower than the
    # generic freshness window (for example a daily bulletin).
    freshness_fresh_after_seconds: int | None = None
    freshness_stale_after_seconds: int = 7200
    freshness_very_stale_after_seconds: int = 21600

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or default_settings
        self._runtime_failures = 0
        self._circuit_open_until: datetime | None = None
        self._last_success_at: str | None = None
        self._last_attempt_at: str | None = None
        self._last_error: str | None = None
        self._durations: list[float] = []

    # -- lifecycle ------------------------------------------------------
    def is_enabled(self) -> bool:
        return True

    def validate_config(self) -> tuple[bool, str | None]:
        """Return ``(satisfied, note)``. Never raises."""
        return True, None

    async def fetch_raw(self) -> list[dict]:  # pragma: no cover - abstract
        raise NotImplementedError

    def normalise(self, record: dict) -> dict | None:
        from ..normalize import normalize_article

        return normalize_article(record, provider=self.key)

    # -- circuit breaker -------------------------------------------------
    def circuit_is_open(self) -> bool:
        if self._circuit_open_until is None:
            return False
        if datetime.now(timezone.utc) >= self._circuit_open_until:
            self._circuit_open_until = None
            self._runtime_failures = 0
            return False
        return True

    def _record_failure(self, message: str) -> None:
        self._runtime_failures += 1
        self._last_error = message
        threshold = max(1, self.config.provider_circuit_failure_threshold)
        if self._runtime_failures >= threshold:
            cooldown = max(30, self.config.provider_circuit_cooldown_seconds)
            self._circuit_open_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown)
            logger.warning(
                "[PROVIDER] %s circuit opened for %ss after %s consecutive failures",
                self.key,
                cooldown,
                self._runtime_failures,
            )

    def _record_success(self, duration_ms: float) -> None:
        self._runtime_failures = 0
        self._last_error = None
        self._last_success_at = utc_now_iso()
        self._durations = (self._durations + [duration_ms])[-20:]

    def _record_transient(self, duration_ms: float) -> None:
        """Recovered after retries: healthy again, but flagged degraded."""
        self._runtime_failures = 0
        self._last_success_at = utc_now_iso()
        self._durations = (self._durations + [duration_ms])[-20:]

    # -- execution -------------------------------------------------------
    async def collect(self, trigger: str = "manual") -> CollectionResult:
        """Run one bounded collection with retries and health tracking."""
        result = CollectionResult(provider=self.key, status=HEALTHY)
        self._last_attempt_at = utc_now_iso()

        if not self.is_enabled():
            return result.finish(DISABLED)

        satisfied, note = self.validate_config()
        if not satisfied:
            result.details["config_note"] = note
            return result.finish(NOT_CONFIGURED)

        if self.circuit_is_open():
            until = self._circuit_open_until.isoformat() if self._circuit_open_until else None
            result.errors.append(
                f"Provider circuit is open after repeated failures (until {until})."
            )
            return result.finish(UNAVAILABLE)

        attempts = max(1, self.config.provider_max_retries)
        delay = max(0.0, self.config.provider_retry_backoff_seconds)
        start = time.perf_counter()
        raw_records: list[dict] = []

        for attempt in range(1, attempts + 1):
            try:
                raw_records = await asyncio.wait_for(
                    self.fetch_raw(),
                    timeout=max(5.0, self.config.ingestion_timeout_seconds * 3),
                )
                if raw_records is None:
                    raw_records = []
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - provider errors are data
                message = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "[PROVIDER] %s fetch attempt %s/%s failed: %s",
                    self.key, attempt, attempts, message,
                )
                result.errors.append(f"Attempt {attempt}: {message}")
                if attempt >= attempts:
                    self._record_failure(message)
                    duration = round((time.perf_counter() - start) * 1000, 2)
                    result.duration_ms = duration
                    return result.finish(UNAVAILABLE)
                await asyncio.sleep(delay * (2 ** (attempt - 1)))

        duration = round((time.perf_counter() - start) * 1000, 2)
        result.records_received = len(raw_records)

        accepted: list[dict] = []
        for record in raw_records:
            try:
                normalised = self.normalise(record)
            except Exception as exc:  # noqa: BLE001
                result.records_failed += 1
                message = f"normalise failed for {record.get('url') or record.get('id')}: {exc}"
                if len(result.errors) < 10:
                    result.errors.append(message)
                continue
            if normalised is None:
                result.records_rejected += 1
                continue
            accepted.append(normalised)

        result.articles = accepted
        result.records_accepted = len(accepted)
        result.duration_ms = duration

        if result.errors and accepted:
            # Some retries failed before succeeding: usable but degraded, and the
            # error history is preserved for the health view.
            self._record_transient(duration)
            return result.finish(DEGRADED)
        if not accepted and raw_records:
            self._record_failure("No records passed validation")
            return result.finish(DEGRADED)

        self._record_success(duration)
        return result.finish(HEALTHY)

    # -- health ----------------------------------------------------------
    def health(self, stored: dict | None = None) -> ProviderHealth:
        satisfied, note = self.validate_config()
        stored = stored or {}
        circuit_open_until = (
            self._circuit_open_until.isoformat() if self._circuit_open_until else None
        )

        never_attempted = not (
            stored.get("last_attempt_at") or self._last_attempt_at
        )
        if not self.is_enabled():
            status = DISABLED
        elif not satisfied:
            status = NOT_CONFIGURED
        elif self.circuit_is_open() or self._last_error:
            # A provider whose most recent collection failed is not healthy,
            # even if it is not yet circuit-broken.
            status = UNAVAILABLE
        elif stored.get("circuit_open_until"):
            status = UNAVAILABLE
        elif stored.get("consecutive_failures"):
            status = DEGRADED
        elif never_attempted:
            # Reporting "healthy" before a single collection has run would be a
            # claim the system cannot back up.
            status = IDLE
        else:
            status = HEALTHY

        avg = None
        if self._durations:
            avg = round(sum(self._durations) / len(self._durations), 2)
        elif stored.get("avg_duration_ms"):
            avg = stored["avg_duration_ms"]

        return ProviderHealth(
            provider=self.key,
            name=self.name,
            provider_type=self.provider_type,
            enabled=self.is_enabled(),
            config_satisfied=satisfied,
            status=status,
            last_attempt_at=stored.get("last_attempt_at") or self._last_attempt_at,
            last_success_at=stored.get("last_success_at") or self._last_success_at,
            last_error=stored.get("last_error") or self._last_error,
            consecutive_failures=stored.get("consecutive_failures", self._runtime_failures),
            circuit_open_until=stored.get("circuit_open_until") or circuit_open_until,
            avg_duration_ms=avg,
            notes=note,
            docs_url=self.docs_url,
            requires_credentials=self.requires_credentials,
            verification_status=self.verification_status,
        )
