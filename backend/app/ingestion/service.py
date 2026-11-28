"""Ingestion orchestration.

Responsibilities, in order:

1. run the requested providers (each isolated, retried, health-recorded);
2. normalise and validate every record;
3. deduplicate articles against what is already stored;
4. classify, geolocate and assess articles;
5. cluster articles into events, or upsert structured observations;
6. recompute event statistics, assessments, timeline and relationships;
7. evaluate alert rules and schedule RAG indexing.

Provider isolation is enforced by ``asyncio.gather(..., return_exceptions=True)``
per provider *and* by the adapter's own error handling: one failing source can
never prevent the others from collecting.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from ..config import settings
from ..database.db import get_connection, write_connection
from ..intelligence.assessment import build_event_assessment, record_timeline_entry
from ..intelligence.classification import classify_article
from ..intelligence.clustering import (
    SAME_EVENT,
    compare_events,
    derive_event_state,
    find_related_events,
)
from ..intelligence.deduplication import (
    assess_independence,
    compare_articles,
)
from ..intelligence.geolocation import extract_location
from ..intelligence.importance import calculate_importance_score
from ..intelligence.source_catalog import credibility_score, source_metadata
from ..intelligence.taxonomy import TAXONOMY_VERSION
from .normalize import normalize_article, to_utc_iso, utc_now
from .registry import PROVIDERS, record_run

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()

# Providers run on every manual/bulk collection cycle. Structured providers are
# cheaper and more valuable, so they are included by default too.
DEFAULT_CYCLE_PROVIDERS = ("rss", "gdelt", "google_news", "usgs", "who")


def _schedule_rag_indexing() -> None:
    if not settings.rag_enabled:
        return
    try:
        from ..rag.indexer import index_after_ingestion

        task = asyncio.create_task(index_after_ingestion())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RAG] Could not schedule post-ingestion indexing: %s", exc)


# ----------------------------------------------------------------------
# Article storage
# ----------------------------------------------------------------------
def _load_existing_articles(conn) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, title, url, canonical_url, source, publisher, publisher_domain,
                   provider, provider_record_id, published_at, description,
                   content_hash, image_url, first_seen_at, language, reporting_type
            FROM articles
            ORDER BY id DESC
            LIMIT 5000
            """
        ).fetchall()
    ]


def store_article(conn, article: dict, existing: list[dict]) -> tuple[int | None, dict]:
    """Insert or refresh an article. Returns ``(article_id, verdict)``."""
    for candidate in existing:
        verdict = compare_articles(article, candidate)
        if verdict.is_duplicate:
            conn.execute(
                """
                UPDATE articles
                SET last_seen_at = ?,
                    provider = COALESCE(provider, ?)
                WHERE id = ?
                """,
                (to_utc_iso(utc_now()), article.get("provider"), candidate["id"]),
            )
            return None, {"duplicate": True, "kind": verdict.kind, "of": candidate["id"]}

    source_facts = source_metadata(article.get("publisher_domain"), article.get("publisher") or article.get("source"))
    article.update(source_facts)
    article_id = conn.execute(
        """
        INSERT INTO articles (
            title, url, canonical_url, source, publisher, publisher_domain, provider,
            provider_record_id, published_at, source_record_at, description, image_url,
            content_hash, description_hash, language, author, extraction_status,
            reporting_type, syndication_of, event_time, event_time_precision,
            first_seen_at, last_seen_at, is_independent, raw_metadata,
            source_tier, propaganda_risk, state_affiliated, source_region
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article["title"],
            article["url"],
            article.get("canonical_url"),
            article.get("source"),
            article.get("publisher"),
            article.get("publisher_domain"),
            article.get("provider"),
            article.get("provider_record_id"),
            article.get("published_at"),
            article.get("source_record_at"),
            article.get("description"),
            article.get("image_url"),
            article.get("content_hash"),
            article.get("description_hash"),
            article.get("language"),
            article.get("author"),
            article.get("extraction_status"),
            article.get("reporting_type"),
            article.get("syndication_of"),
            article.get("event_time"),
            article.get("event_time_precision"),
            article.get("first_seen_at"),
            article.get("last_seen_at"),
            article.get("is_independent", 1),
            json.dumps(article.get("raw_metadata"), default=str)
            if article.get("raw_metadata")
            else None,
            article.get("source_tier", "undeclared"),
            article.get("propaganda_risk", "medium"),
            int(bool(article.get("state_affiliated", False))),
            article.get("source_region"),
        ),
    ).lastrowid
    existing.append({**article, "id": article_id})
    return article_id, {"duplicate": False}


# ----------------------------------------------------------------------
# Event classification of an article
# ----------------------------------------------------------------------
def _ai_classification_allowed() -> bool:
    return bool(settings.ollama_enabled and settings.ai_classification_enabled)


async def classify_for_ingestion(article: dict, ai_budget: dict) -> dict:
    """Deterministic classification, optionally refined by the model."""
    deterministic = classify_article(article)

    if (
        not _ai_classification_allowed()
        or ai_budget["remaining"] <= 0
        or deterministic["confidence"] >= settings.ai_classification_min_confidence
    ):
        return deterministic

    try:
        from ..ai.ollama import analyze_with_ollama
        from ..intelligence.classification import merge_ai_classification

        ai_budget["remaining"] -= 1
        response = await analyze_with_ollama(
            title=article.get("title", ""),
            description=article.get("description", ""),
            source=article.get("source", ""),
            url=article.get("url", ""),
        )
        if not response:
            return deterministic
        ai_response_category = response.get("category")
        if ai_response_category is None:
            return deterministic
        return merge_ai_classification(
            deterministic,
            ai_response_category,
            response.get("confidence"),
            response.get("subcategory"),
        )
    except Exception as exc:  # noqa: BLE001 - AI is optional
        logger.warning("[AI] classification failed for %s: %s", article.get("url"), exc)
        return deterministic


# ----------------------------------------------------------------------
# Event upsert
# ----------------------------------------------------------------------
def _event_payload(article: dict, classification: dict) -> dict:
    text = f"{article.get('title', '')}. {article.get('description', '')}"
    location = extract_location(
        text,
        fallback_country=article.get("country"),
        fallback_country_code=article.get("country_code"),
    )
    return {
        "title": article.get("title") or "Untitled",
        "summary": (article.get("description") or article.get("title") or "")[:1200],
        "category": classification["category"],
        "subcategory": classification.get("subcategory") or "unclassified",
        "classification_confidence": classification.get("confidence"),
        "classification_method": classification.get("method", "deterministic"),
        "country": location.country,
        "country_code": location.country_code,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "location_precision": location.precision,
        "location_text": location.location_text,
        "geocoding_source": location.source,
        "geocoding_confidence": location.confidence,
        "occurred_at": article.get("event_time") or article.get("published_at"),
        "occurred_at_precision": article.get("event_time_precision") or (
            "timestamp" if article.get("published_at") else "unknown"
        ),
        "provider_key": article.get("provider"),
    }


def _recompute_event_statistics(conn, event_id: int) -> dict:
    """Recompute everything derived from the event's articles."""
    articles = [
        dict(row)
        for row in conn.execute(
            """
            SELECT a.id, a.title, a.url, a.description, a.source, a.publisher,
                   a.publisher_domain, a.published_at, a.first_seen_at,
                   a.reporting_type, a.content_hash, a.is_independent, a.provider,
                   a.source_tier, a.propaganda_risk, a.state_affiliated, a.source_region
            FROM articles a
            JOIN event_articles ea ON ea.article_id = a.id
            WHERE ea.event_id = ?
            ORDER BY COALESCE(a.published_at, a.first_seen_at), a.id
            """,
            (event_id,),
        ).fetchall()
    ]
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        return {}
    # Structured observations (USGS record, CAP alert) legitimately have no news
    # article attached; their assessment must still be computed.
    if not articles and not event["is_structured_observation"]:
        return {}

    independence = assess_independence(articles, settings.syndication_domain_set)

    # Provenance and statistics. Structured observations have no articles,
    # so keep the provider attribution stored at upsert time; overwriting
    # it with an empty join would erase provider_keys (breaking structured
    # dedupe, provider boosts and advisory/conflict-history floors).
    providers = sorted({a["provider"] for a in articles if a.get("provider")})
    if not providers and event["provider_keys"]:
        providers = [
            key.strip()
            for key in str(event["provider_keys"]).split(",")
            if key.strip()
        ]
    source_domains = ", ".join(independence.publisher_families)
    if not source_domains and event["source_domains"]:
        source_domains = event["source_domains"]
    published = [a["published_at"] for a in articles if a.get("published_at")]
    first_seen = min(
        [a.get("first_seen_at") or a.get("published_at") for a in articles if a.get("first_seen_at") or a.get("published_at")],
        default=None,
    )
    last_seen = (
        max(published, default=None)
        or event["updated_at"]
        or event["last_seen_at"]
        or to_utc_iso(utc_now())
    )
    first_seen = first_seen or event["first_seen_at"] or event["created_at"]

    reported_casualties = None
    if event["is_structured_observation"]:
        try:
            attributes = json.loads(event["data_sources"]) if event["data_sources"] else {}
        except (TypeError, ValueError):
            attributes = {}
        reported_casualties = attributes.get("fatalities") if isinstance(attributes, dict) else None
    if not reported_casualties:
        from .normalize import extract_reported_casualties

        candidates = [
            extract_reported_casualties(f"{a['title']}. {a['description'] or ''}")
            for a in articles
        ]
        candidates = [value for value in candidates if value]
        reported_casualties = max(candidates) if candidates else None

    assessment = build_event_assessment(
        event=dict(event),
        articles=articles,
        independence=independence,
        reported_casualties=reported_casualties,
    )
    credibility = credibility_score(articles)
    entity_names = [row[0] for row in conn.execute(
        "SELECT e.name FROM event_entity_mentions m JOIN entities e ON e.id=m.entity_id WHERE m.event_id=?",
        (event_id,),
    ).fetchall()]
    ranking = calculate_importance_score(dict(event), articles, entity_names)

    now_iso = to_utc_iso(utc_now())
    conn.execute(
        """
        UPDATE events SET
            article_count = ?, source_count = ?, unique_source_count = ?,
            independent_source_count = ?, syndicated_source_count = ?,
            corroboration_level = ?, first_seen_at = ?, last_seen_at = ?,
            source_domains = ?, provider_keys = ?,
            severity = ?, severity_label = ?, severity_components = ?,
            confidence = ?, confidence_components = ?, confidence_explanation = ?,
            priority_score = ?, priority_label = ?,
            importance = ?, importance_score = ?, credibility_score = ?, assessment_updated_at = ?,
            event_state = ?, event_state_updated_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            len(articles),
            len(independence.publisher_families) or 1,
            independence.independent_publishers or 1,
            independence.independent_publishers,
            independence.syndicated_publishers,
            assessment["corroboration_level"],
            first_seen,
            last_seen,
            source_domains,
            ", ".join(providers),
            assessment["severity"]["score"],
            assessment["severity"]["label"],
            json.dumps(assessment["severity"]),
            assessment["confidence"]["score"],
            json.dumps(assessment["confidence"]),
            json.dumps(assessment["confidence_explanation"]),
            assessment["priority"]["score"],
            assessment["priority"]["label"],
            assessment["importance"],
            ranking["score"],
            credibility,
            now_iso,
            assessment["state"],
            now_iso,
            now_iso,
            event_id,
        ),
    )

    if not event["occurred_at"]:
        conn.execute(
            "UPDATE events SET occurred_at = COALESCE(?, occurred_at) WHERE id = ?",
            (event["event_time"] or first_seen, event_id),
        )

    for note in independence.notes:
        record_timeline_entry(
            conn, event_id, now_iso, "provenance_update", note
        )

    # Entity intelligence: extracted deterministically, never merged on name
    # similarity alone (type is part of the identity key).
    try:
        from ..intelligence.entities import extract_for_event

        extract_for_event(conn, dict(event), articles)
    except Exception:  # noqa: BLE001 - entity extraction must not break ingestion
        logger.exception("[ENTITIES] extraction failed for event %s", event_id)

    return assessment


def _create_event_from_article(conn, article: dict, payload: dict) -> int:
    now_iso = to_utc_iso(utc_now())
    event_id = conn.execute(
        """
        INSERT INTO events (
            title, summary, category, subcategory, taxonomy_version,
            classification_method, classification_confidence,
            country, country_code, latitude, longitude,
            location_precision, location_text, geocoding_source, geocoding_confidence,
            importance, confidence, article_count, source_count, unique_source_count,
            independent_source_count, syndicated_source_count, corroboration_level,
            first_seen_at, last_seen_at, source_domains, provider_keys,
            event_time, occurred_at, occurred_at_precision, observed_at,
            event_state, event_state_updated_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 5, 0.3, 1, 1, 1, 0, 0, 'single',
                  ?, ?, ?, ?, ?, ?, ?, ?, 'newly_detected', ?, ?, ?)
        """,
        (
            payload["title"],
            payload["summary"],
            payload["category"],
            payload["subcategory"],
            TAXONOMY_VERSION,
            payload["classification_method"],
            payload["classification_confidence"],
            payload["country"],
            payload["country_code"],
            payload["latitude"],
            payload["longitude"],
            payload["location_precision"],
            payload.get("location_text"),
            payload.get("geocoding_source"),
            payload.get("geocoding_confidence"),
            article.get("first_seen_at") or article.get("published_at") or now_iso,
            article.get("published_at") or now_iso,
            ", ".join([article.get("publisher_domain") or article.get("source") or ""]).strip(", "),
            payload.get("provider_key"),
            payload.get("occurred_at") or article.get("published_at"),
            payload.get("occurred_at"),
            payload.get("occurred_at_precision") or "unknown",
            article.get("first_seen_at") or now_iso,
            now_iso,
            now_iso,
            now_iso,
        ),
    ).lastrowid
    return event_id


def _merge_article(conn, event_id: int, article_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO event_articles (event_id, article_id) VALUES (?, ?)",
        (event_id, article_id),
    )


def _store_relationship(conn, source_id: int, target_id: int, relationship: str, confidence: float, reason: str, evidence: dict) -> None:
    conn.execute(
        """
        INSERT INTO event_relationships (
            source_event_id, target_event_id, relationship, confidence, reason, evidence
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_event_id, target_event_id, relationship) DO UPDATE SET
            confidence = excluded.confidence,
            reason = excluded.reason,
            evidence = excluded.evidence
        """,
        (source_id, target_id, relationship, confidence, reason, json.dumps(evidence, default=str)),
    )


def _upsert_structured_observation(conn, observation: dict) -> tuple[int, bool]:
    """Create or update an event from a structured provider record."""
    provider = observation.get("provider")
    record_id = observation.get("provider_record_id") or observation.get("url")
    existing = conn.execute(
        """
        SELECT id FROM events
        WHERE provider_keys = ? AND (
            title = ? OR (source_domains LIKE ? AND occurred_at = ?)
        )
        ORDER BY id DESC LIMIT 1
        """,
        (provider, observation.get("title"), f"%{provider}%", observation.get("event_time")),
    ).fetchone()

    now_iso = to_utc_iso(utc_now())
    occurred = observation.get("event_time") or observation.get("published_at")
    attributes = observation.get("attributes") or {}

    if existing:
        event_id = existing["id"]
        conn.execute(
            """
            UPDATE events SET
                title = ?, summary = ?, updated_at = ?, last_seen_at = ?,
                occurred_at = COALESCE(?, occurred_at),
                data_sources = ?, severity = COALESCE(?, severity)
            WHERE id = ?
            """,
            (
                observation.get("title"),
                observation.get("summary"),
                now_iso,
                now_iso,
                occurred,
                json.dumps(attributes, default=str),
                observation.get("severity_hint"),
                event_id,
            ),
        )
        record_timeline_entry(
            conn, event_id, now_iso, "observation_update",
            f"Provider {provider} updated record {record_id}."
        )
        return event_id, False

    event_id = conn.execute(
        """
        INSERT INTO events (
            title, summary, category, subcategory, taxonomy_version,
            classification_method, classification_confidence,
            country, country_code, latitude, longitude,
            location_precision, location_text, geocoding_source, geocoding_confidence,
            importance, confidence, article_count, source_count, unique_source_count,
            independent_source_count, corroboration_level, source_domains, provider_keys,
            data_sources, is_structured_observation,
            event_time, occurred_at, occurred_at_precision, observed_at,
            event_state, event_state_updated_at, first_seen_at, last_seen_at,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'provider_structured', 0.9, ?, ?, ?, ?, ?, ?, ?, ?,
                  5, 0.5, 0, 1, 1, 1, 'single', ?, ?, ?, 1,
                  ?, ?, ?, ?, 'newly_detected', ?, ?, ?, ?, ?)
        """,
        (
            observation.get("title"),
            observation.get("summary"),
            observation.get("category"),
            observation.get("subcategory"),
            TAXONOMY_VERSION,
            observation.get("country"),
            observation.get("country_code"),
            observation.get("latitude"),
            observation.get("longitude"),
            observation.get("location_precision") or "unknown",
            observation.get("location_text"),
            provider,
            0.9,
            provider,
            provider,
            json.dumps(attributes, default=str),
            occurred,
            occurred,
            "timestamp",
            observation.get("observed_at"),
            now_iso,
            now_iso,
            now_iso,
            now_iso,
            now_iso,
        ),
    ).lastrowid

    record_timeline_entry(
        conn, event_id, occurred or now_iso, "initial_detection",
        f"First structured observation received from {provider}."
    )
    return event_id, True


# ----------------------------------------------------------------------
# Provider execution
# ----------------------------------------------------------------------
async def _run_provider(key: str, trigger: str):
    """Collect one provider. Never raises: failures become a result object."""
    provider = PROVIDERS.get(key)
    if provider is None:
        return None
    try:
        return await provider.collect(trigger=trigger)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - one provider must not break the cycle
        from .providers.base import CollectionResult

        logger.exception("[PROVIDER] %s raised during collection", key)
        return CollectionResult(
            provider=key, status="unavailable", errors=[f"{type(exc).__name__}: {exc}"]
        ).finish("unavailable")


async def collect_providers(keys: list[str] | None = None, trigger: str = "manual") -> list:
    keys = keys or list(DEFAULT_CYCLE_PROVIDERS)
    results = await asyncio.gather(
        *(_run_provider(key, trigger) for key in keys), return_exceptions=True
    )
    return [result for result in results if result is not None and not isinstance(result, Exception)]


# ----------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------
async def ingest(providers: list[str] | None = None, trigger: str = "manual") -> dict:
    started = utc_now()
    results = await collect_providers(providers, trigger=trigger)

    ai_budget = {"remaining": max(0, settings.ai_classification_max_per_cycle)}
    counters = {
        "providers_run": len(results),
        "articles_seen": 0,
        "articles_inserted": 0,
        "duplicates_removed": 0,
        "articles_rejected": 0,
        "events_created": 0,
        "events_updated": 0,
        "structured_events_created": 0,
        "structured_events_updated": 0,
        "ai_analyzed": 0,
        "ai_failed": 0,
        "provider_errors": [],
    }
    per_provider: list[dict] = []

    article_records: list[dict] = []
    observation_records: list[dict] = []
    for result in results:
        per_provider.append(result.as_dict())
        counters["provider_errors"].extend(result.errors)
        provider = PROVIDERS.get(result.provider)
        if provider and provider.produces_structured_observations:
            observation_records.extend(result.articles)
        else:
            article_records.extend(result.articles)

    max_articles = max(1, settings.ingestion_max_articles_per_cycle)
    article_records = article_records[:max_articles]
    counters["articles_seen"] = len(article_records)

    with write_connection() as conn:
        existing_articles = _load_existing_articles(conn)
        existing_events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, summary, category, subcategory, country, country_code,
                       latitude, longitude, location_precision, importance, confidence,
                       event_time, occurred_at, article_count, independent_source_count
                FROM events
                WHERE is_structured_observation = 0
                ORDER BY event_time DESC
                LIMIT 2000
                """
            ).fetchall()
        ]

        new_relationships: list[dict] = []

        for article in article_records:
            article_id, verdict = store_article(conn, article, existing_articles)
            if article_id is None:
                counters["duplicates_removed"] += 1
                continue
            counters["articles_inserted"] += 1

            classification = await classify_for_ingestion(article, ai_budget)
            if classification.get("method") == "ai_assisted":
                counters["ai_analyzed"] += 1

            payload = _event_payload(article, classification)

            best_event, best_score = None, 0.0
            for event in existing_events:
                comparison = compare_events(payload, event)
                if comparison.decision == SAME_EVENT and comparison.score > best_score:
                    best_event, best_score = event, comparison.score
                elif comparison.decision in {"related_event", "similar_event"}:
                    new_relationships.append(
                        {
                            "target_title": event.get("title"),
                            "target_id": event.get("id"),
                            "relationship": "related_to"
                            if comparison.decision == "related_event"
                            else "similar_to",
                            "confidence": comparison.score,
                            "reason": comparison.reason,
                            "evidence": comparison.signals,
                        }
                    )

            if best_event:
                event_id = best_event["id"]
                _merge_article(conn, event_id, article_id)
                counters["events_updated"] += 1
            else:
                event_id = _create_event_from_article(conn, article, payload)
                _merge_article(conn, event_id, article_id)
                existing_events.append(
                    {
                        "id": event_id,
                        "title": payload["title"],
                        "summary": payload["summary"],
                        "category": payload["category"],
                        "subcategory": payload["subcategory"],
                        "country": payload["country"],
                        "country_code": payload["country_code"],
                        "latitude": payload["latitude"],
                        "longitude": payload["longitude"],
                        "location_precision": payload["location_precision"],
                        "event_time": payload["occurred_at"],
                        "occurred_at": payload["occurred_at"],
                        "article_count": 1,
                    }
                )
                counters["events_created"] += 1
                record_timeline_entry(
                    conn, event_id, article.get("published_at") or to_utc_iso(utc_now()),
                    "initial_report",
                    f"First report from {article.get('publisher') or article.get('source') or 'unknown source'}.",
                    article_id=article_id,
                )

            _recompute_event_statistics(conn, event_id)

            for relationship in new_relationships[-3:]:
                if relationship["target_id"] and relationship["target_id"] != event_id:
                    _store_relationship(
                        conn, event_id, relationship["target_id"],
                        relationship["relationship"], relationship["confidence"],
                        relationship["reason"], relationship["evidence"],
                    )

        # Structured observations (USGS, WHO, CAP, FIRMS, ReliefWeb, ACLED)
        for observation in observation_records:
            try:
                event_id, created = _upsert_structured_observation(conn, observation)
            except Exception:  # noqa: BLE001
                logger.exception("[INGESTION] structured observation failed")
                continue
            if created:
                counters["structured_events_created"] += 1
                counters["events_created"] += 1
            else:
                counters["structured_events_updated"] += 1
                counters["events_updated"] += 1
            _recompute_event_statistics(conn, event_id)

        # Attach per-provider event counters before the runs are persisted.
        for result in results:
            provider = PROVIDERS.get(result.provider)
            if provider and provider.produces_structured_observations:
                result.events_created = counters["structured_events_created"]
                result.events_updated = counters["structured_events_updated"]
            else:
                result.events_created = max(0, counters["events_created"] - counters["structured_events_created"])
                result.events_updated = counters["events_updated"]

    # Alert evaluation + RAG indexing happen after the write transaction.
    alerts_created = 0
    try:
        from ..alerts.evaluator import evaluate_all_rules

        alerts_created = evaluate_all_rules()
    except Exception:  # noqa: BLE001 - alerts must never break ingestion
        logger.exception("[ALERTS] evaluation failed")

    _schedule_rag_indexing()

    # Exactly one run row per provider per cycle, written after counters are set.
    for result in results:
        try:
            record_run(result, trigger=trigger)
        except Exception:  # noqa: BLE001 - health persistence must not break ingest
            logger.exception("[PROVIDER] failed to record run for %s", result.provider)

    try:
        from ..intelligence.digest_cache import invalidate_snapshots
        invalidate_snapshots()
    except Exception:  # noqa: BLE001 - cache invalidation cannot fail ingestion
        logger.exception("[CACHE] digest invalidation failed after ingestion")

    finished = utc_now()
    return {
        **counters,
        "alerts_created": alerts_created,
        "providers": per_provider,
        "started_at": to_utc_iso(started),
        "finished_at": to_utc_iso(finished),
        "duration_ms": round((finished - started).total_seconds() * 1000, 2),
    }


async def ingest_provider(key: str, trigger: str = "manual") -> dict:
    return await ingest(providers=[key], trigger=trigger)
