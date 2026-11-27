"""Provider registry and persistent provider/collection health.

The registry is the single place that knows which providers exist, whether they
are configured, and how they have been behaving.  Health is persisted in the
``providers``/``collection_runs`` tables introduced by migration 4 so the UI can
show real history rather than the state of the current process.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..config import settings
from ..database.db import get_connection, write_connection
from .providers.base import (
    DISABLED,
    NOT_CONFIGURED,
    CollectionResult,
    SourceProvider,
)
from .providers.news import GdeltProvider, GoogleNewsProvider, RssProvider
from .providers.structured import (
    AcledProvider,
    CapAlertProvider,
    EonetProvider,
    FirmsWildfireProvider,
    GdacsProvider,
    ReliefWebProvider,
    UsgsEarthquakeProvider,
    WhoOutbreakProvider,
)

logger = logging.getLogger(__name__)


def build_providers() -> dict[str, SourceProvider]:
    providers: dict[str, SourceProvider] = {}
    for provider_class in (
        RssProvider,
        GdeltProvider,
        GoogleNewsProvider,
        UsgsEarthquakeProvider,
        EonetProvider,
        GdacsProvider,
        ReliefWebProvider,
        WhoOutbreakProvider,
        FirmsWildfireProvider,
        CapAlertProvider,
        AcledProvider,
    ):
        provider = provider_class()
        providers[provider.key] = provider
    return providers


# Process-wide registry (providers are stateless apart from health counters).
PROVIDERS: dict[str, SourceProvider] = build_providers()

INTERVAL_SETTING_BY_KEY = {
    "rss": "scheduler_rss_interval_seconds",
    "gdelt": "scheduler_gdelt_interval_seconds",
    "google_news": "scheduler_google_news_interval_seconds",
    "usgs": "scheduler_usgs_interval_seconds",
    "eonet": "scheduler_eonet_interval_seconds",
    "gdacs": "scheduler_gdacs_interval_seconds",
    "reliefweb": "scheduler_reliefweb_interval_seconds",
    "who": "scheduler_who_interval_seconds",
    "firms": "scheduler_firms_interval_seconds",
    "cap": "scheduler_cap_interval_seconds",
}


def provider_interval_seconds(key: str) -> int:
    setting_name = INTERVAL_SETTING_BY_KEY.get(key)
    if setting_name:
        return int(getattr(settings, setting_name, 1800))
    return int(getattr(PROVIDERS.get(key), "default_interval_seconds", 1800))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_provider_rows() -> None:
    """Upsert registry metadata so the providers table always reflects config."""
    with write_connection() as conn:
        for provider in PROVIDERS.values():
            satisfied, note = provider.validate_config()
            conn.execute(
                """
                INSERT INTO providers (
                    key, name, provider_type, enabled, config_satisfied,
                    config_notes, docs_url, requires_credentials, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    name = excluded.name,
                    provider_type = excluded.provider_type,
                    enabled = excluded.enabled,
                    config_satisfied = excluded.config_satisfied,
                    config_notes = excluded.config_notes,
                    docs_url = excluded.docs_url,
                    requires_credentials = excluded.requires_credentials,
                    updated_at = excluded.updated_at
                """,
                (
                    provider.key,
                    provider.name,
                    provider.provider_type,
                    1 if provider.is_enabled() else 0,
                    1 if satisfied else 0,
                    note,
                    provider.docs_url,
                    1 if provider.requires_credentials else 0,
                    _utc_now_iso(),
                ),
            )


def load_provider_state() -> dict[str, dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM providers").fetchall()
        return {row["key"]: dict(row) for row in rows}
    finally:
        conn.close()


def record_run(result: CollectionResult, trigger: str = "manual") -> int:
    """Persist a collection run and fold its outcome into provider health."""
    now = _utc_now_iso()
    with write_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO collection_runs (
                provider_key, trigger, status, started_at, finished_at, duration_ms,
                records_received, records_accepted, records_rejected, records_duplicate,
                records_failed, events_created, events_updated, error, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.provider,
                trigger,
                result.status,
                result.started_at,
                result.finished_at or now,
                result.duration_ms,
                result.records_received,
                result.records_accepted,
                result.records_rejected,
                result.records_duplicate,
                result.records_failed,
                result.events_created,
                result.events_updated,
                ("; ".join(result.errors)[:2000] if result.errors else None),
                json.dumps(result.details, default=str)[:4000],
            ),
        )
        run_id = cursor.lastrowid

        row = conn.execute(
            "SELECT consecutive_failures, avg_duration_ms FROM providers WHERE key = ?",
            (result.provider,),
        ).fetchone()

        success = result.status in {"healthy", "degraded"}
        failures = 0 if success else (row["consecutive_failures"] if row else 0) + 1
        avg = row["avg_duration_ms"] if row else None
        if result.duration_ms and success:
            avg = (
                result.duration_ms
                if avg is None
                else round((avg * 0.7) + (result.duration_ms * 0.3), 2)
            )

        conn.execute(
            """
            UPDATE providers SET
                last_attempt_at = ?,
                last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END,
                last_error = CASE WHEN ? THEN last_error ELSE ? END,
                consecutive_failures = ?,
                avg_duration_ms = ?,
                updated_at = ?
            WHERE key = ?
            """,
            (
                result.finished_at or now,
                1 if success else 0,
                result.finished_at or now,
                1 if success else 0,
                ("; ".join(result.errors)[:1000] if result.errors else f"status={result.status}"),
                failures,
                avg,
                now,
                result.provider,
            ),
        )
    return run_id


def provider_health_payload(include_history: bool = False) -> list[dict]:
    """Health for every registered provider plus recent run history."""
    stored = load_provider_state()
    payload = []
    conn = get_connection()
    try:
        for key, provider in PROVIDERS.items():
            state = stored.get(key, {})
            health = provider.health(state).as_dict()
            runs = conn.execute(
                """
                SELECT status, started_at, finished_at, duration_ms,
                       records_received, records_accepted, records_duplicate,
                       records_failed, events_created, events_updated, error
                FROM collection_runs
                WHERE provider_key = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (key, 10 if include_history else 3),
            ).fetchall()
            health["recent_runs"] = [dict(run) for run in runs]
            health["interval_seconds"] = provider_interval_seconds(key)
            health["produces_structured_observations"] = provider.produces_structured_observations

            latest = runs[0] if runs else None
            health["last_run_status"] = latest["status"] if latest else None
            health["records_last_run"] = latest["records_received"] if latest else 0

            # Freshness: how long since the last successful collection.
            last_success = health.get("last_success_at")
            if last_success and health["enabled"] and health["config_satisfied"]:
                try:
                    age = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(last_success)
                    ).total_seconds()
                    if age > provider_interval_seconds(key) * 3:
                        health["status"] = "degraded"
                        health["staleness_seconds"] = int(age)
                        health["notes"] = (
                            "No successful collection for longer than three "
                            "configured intervals."
                        )
                except ValueError:
                    pass
            payload.append(health)
        return payload
    finally:
        conn.close()


def collection_history(provider_key: str | None = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    try:
        if provider_key:
            rows = conn.execute(
                "SELECT * FROM collection_runs WHERE provider_key = ? ORDER BY id DESC LIMIT ?",
                (provider_key, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM collection_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            if item.get("details"):
                try:
                    item["details"] = json.loads(item["details"])
                except (TypeError, ValueError):
                    pass
            results.append(item)
        return results
    finally:
        conn.close()


def enabled_provider_keys() -> list[str]:
    return [
        key
        for key, provider in PROVIDERS.items()
        if provider.is_enabled() and provider.validate_config()[0]
    ]


def provider_status_summary() -> dict:
    health = provider_health_payload()
    counts: dict[str, int] = {}
    for item in health:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "providers": len(health),
        "by_status": counts,
        "healthy": counts.get("healthy", 0),
        "degraded": counts.get("degraded", 0),
        "unavailable": counts.get("unavailable", 0),
        "not_configured": counts.get("not_configured", 0),
        "disabled": counts.get("disabled", 0),
        "generated_at": _utc_now_iso(),
    }
