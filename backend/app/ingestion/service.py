import asyncio
import logging
from datetime import datetime, timezone

from .gdelt import fetch_gdelt
from .google_news import fetch_google_news
from .rss import fetch_rss

from ..ai.ollama import analyze_with_ollama
from ..config import settings
from ..database.db import write_connection
from ..intelligence.classification import classify_article, normalize_category
from ..intelligence.clustering import find_matching_event
from ..intelligence.confidence import score_event_confidence
from ..intelligence.deduplication import create_article_hash, find_duplicate_article
from ..intelligence.importance import score_event_importance
from ..intelligence.verification import determine_corroboration_level
from ..processing.analyzer import analyze

_background_tasks: set[asyncio.Task] = set()


def _schedule_rag_indexing():
    """Kick off Phase 3 indexing in the background after ingestion."""
    if not settings.rag_enabled:
        return
    try:
        from ..rag.indexer import index_after_ingestion
        task = asyncio.create_task(index_after_ingestion())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except Exception as exc:
        logger.warning("[RAG] Could not schedule post-ingestion indexing: %s", exc)


logger = logging.getLogger(__name__)


def _event_time_from_article(article):
    value = article.get("published_at") or article.get("event_time")
    return value or datetime.now(timezone.utc).isoformat()


def _normalize_event_record(article, analysis):
    category = normalize_category(
        (article.get("category") or analysis.get("category") or "other")
    )
    title = (article.get("title") or analysis.get("title") or "Untitled").strip()
    summary = (
        article.get("summary")
        or analysis.get("summary")
        or article.get("description")
        or title
    ).strip()
    country = article.get("country") or analysis.get("country")
    country_code = article.get("country_code") or analysis.get("country_code")
    latitude = (
        article.get("latitude")
        if article.get("latitude") is not None
        else analysis.get("latitude")
    )
    longitude = (
        article.get("longitude")
        if article.get("longitude") is not None
        else analysis.get("longitude")
    )
    importance_base = int(analysis.get("importance") or 5)
    importance = score_event_importance(
        {
            "severity": importance_base,
            "geographic_impact": 6 if country else 3,
            "source_coverage": 3,
            "human_impact": 5 if "alert" in title.lower() or "dead" in title.lower() else 4,
            "economic_impact": 4,
            "urgency": 6,
        }
    )
    confidence_base = float(analysis.get("confidence") or 0.5)
    return {
        "title": title,
        "summary": summary,
        "category": category,
        "country": country,
        "country_code": country_code,
        "latitude": latitude,
        "longitude": longitude,
        "importance": importance,
        "confidence": max(0.0, min(1.0, confidence_base)),
        "event_time": _event_time_from_article(article),
    }


def _update_event_statistics(conn, event_id):
    rows = conn.execute(
        """
        SELECT a.source, a.url, a.published_at
        FROM event_articles ea
        JOIN articles a ON a.id = ea.article_id
        WHERE ea.event_id = ?
        ORDER BY a.published_at DESC, a.id DESC
        """,
        (event_id,),
    ).fetchall()
    if not rows:
        return

    unique_sources = sorted({(row["source"] or "Unknown").strip() for row in rows if row["source"]})
    domains = sorted({
        (row["url"] or "").split("//")[-1].split("/")[0].replace("www.", "")
        for row in rows if row["url"]
    })
    article_count = len(rows)
    source_count = max(1, len(unique_sources))
    unique_source_count = max(1, len(domains))
    first_seen_at = min((row["published_at"] for row in rows if row["published_at"]), default=None)
    last_seen_at = max((row["published_at"] for row in rows if row["published_at"]), default=None)
    corroboration_level = determine_corroboration_level(unique_source_count)

    event_row = conn.execute(
        "SELECT category, country, country_code, title, confidence, importance FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if not event_row:
        return

    base_confidence = float(event_row["confidence"] or 0.5)
    classification_confidence = max(base_confidence, 0.5)
    confidence_score = score_event_confidence(
        {
            "source_count": source_count,
            "article_count": article_count,
            "classification_confidence": classification_confidence,
            "location_confidence": 0.9 if event_row["country_code"] else 0.7,
            "time_confidence": 0.8,
            "article_similarity": min(0.95, 0.6 + (article_count * 0.04)),
        }
    )

    importance_score = score_event_importance(
        {
            "severity": max(event_row["importance"] or 5, 1),
            "geographic_impact": 7 if event_row["country_code"] else 4,
            "source_coverage": min(10, source_count + article_count // 2),
            "human_impact": 6 if "disaster" in (event_row["category"] or "").lower() else 4,
            "economic_impact": 5,
            "urgency": 5 if article_count >= 2 else 3,
        }
    )

    conn.execute(
        """
        UPDATE events
        SET article_count = ?,
            source_count = ?,
            unique_source_count = ?,
            corroboration_level = ?,
            first_seen_at = ?,
            last_seen_at = ?,
            source_domains = ?,
            importance = ?,
            confidence = ?,
            event_time = COALESCE(?, event_time)
        WHERE id = ?
        """,
        (
            article_count,
            source_count,
            unique_source_count,
            corroboration_level,
            first_seen_at,
            last_seen_at,
            ", ".join(domains),
            importance_score,
            round(confidence_score, 2),
            last_seen_at,
            event_id,
        ),
    )


def _merge_article_to_event(conn, event_id, article_id):
    conn.execute(
        "INSERT OR IGNORE INTO event_articles (event_id, article_id) VALUES (?, ?)",
        (event_id, article_id),
    )
    _update_event_statistics(conn, event_id)


async def ingest():
    """Collect free news sources, deduplicate articles, cluster events, and store intelligence."""
    articles = []

    for source_name, fetcher in (
        ("GDELT", lambda: fetch_gdelt(settings.gdelt_max_records)),
        ("RSS", fetch_rss),
        ("Google News RSS", fetch_google_news),
    ):
        try:
            logger.info("[%s] Fetching articles...", source_name)
            fetched = await fetcher()
            articles.extend(fetched)
            logger.info("[%s] Fetched %s articles", source_name, len(fetched))
        except Exception as exc:
            logger.exception("[%s] ERROR: %s", source_name, exc)

    with write_connection() as conn:
        existing_articles = [
            dict(row)
            for row in conn.execute(
                "SELECT id, title, url, source, published_at, description, image_url, content_hash FROM articles"
            ).fetchall()
        ]
        existing_events = [
            dict(row)
            for row in conn.execute(
                "SELECT id, title, summary, category, country, country_code, latitude, longitude, importance, confidence, event_time, article_count, source_count FROM events"
            ).fetchall()
        ]

        inserted = 0
        events_created = 0
        ai_analyzed = 0
        ai_failed = 0
        duplicates_removed = 0

        for article in articles:
            url = (article.get("url") or "").strip()
            if not url:
                continue

            title = article.get("title") or "Untitled"
            description = article.get("description") or ""
            source = article.get("source") or "Unknown"
            article_hash = create_article_hash(title, url)
            article["content_hash"] = article_hash

            if find_duplicate_article(article, existing_articles):
                duplicates_removed += 1
                continue

            deterministic = analyze(title, description)
            classification = classify_article(article)
            event_record = _normalize_event_record(
                article,
                {
                    **deterministic,
                    "category": classification["category"],
                    "confidence": classification["confidence"],
                },
            )

            try:
                logger.info("[AI] Analyzing: %s", title)
                ai_response = await analyze_with_ollama(
                    title=title,
                    description=description,
                    source=source,
                    url=url,
                )
                ai_analyzed += 1
                if ai_response:
                    event_record["title"] = ai_response.get("event_title") or event_record["title"]
                    event_record["summary"] = ai_response.get("summary") or event_record["summary"]
                    event_record["category"] = normalize_category(
                        ai_response.get("category") or event_record["category"]
                    )
                    event_record["country"] = ai_response.get("country") or event_record["country"]
                    event_record["country_code"] = ai_response.get("country_code") or event_record["country_code"]
                    if ai_response.get("latitude") is not None:
                        event_record["latitude"] = ai_response.get("latitude")
                    if ai_response.get("longitude") is not None:
                        event_record["longitude"] = ai_response.get("longitude")
                    event_record["importance"] = score_event_importance(
                        {
                            "severity": int(ai_response.get("importance") or event_record["importance"]),
                            "geographic_impact": 7 if event_record["country_code"] else 4,
                            "source_coverage": 4,
                            "human_impact": 6 if "disaster" in event_record["category"].lower() else 5,
                            "economic_impact": 4,
                            "urgency": 6,
                        }
                    )
                    event_record["confidence"] = max(
                        0.0,
                        min(1.0, float(ai_response.get("confidence") or event_record["confidence"])),
                    )
            except Exception as exc:
                logger.exception("[AI ERROR] %s", exc)
                ai_failed += 1

            article_id = conn.execute(
                """
                INSERT INTO articles (title, url, source, published_at, description, image_url, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    url,
                    source,
                    article.get("published_at") or "",
                    description,
                    article.get("image_url"),
                    article_hash,
                ),
            ).lastrowid
            inserted += 1
            existing_articles.append(
                {
                    "id": article_id,
                    "title": title,
                    "url": url,
                    "source": source,
                    "published_at": article.get("published_at") or "",
                    "description": description,
                    "image_url": article.get("image_url"),
                    "content_hash": article_hash,
                }
            )

            matching_event = find_matching_event(
                {
                    **event_record,
                    "published_at": article.get("published_at") or event_record["event_time"],
                    "url": url,
                    "source": source,
                },
                existing_events,
            )

            if matching_event:
                event_id = matching_event["id"]
                _merge_article_to_event(conn, event_id, article_id)
                event_record.update(
                    {
                        "event_id": event_id,
                        "title": matching_event.get("title") or event_record["title"],
                        "summary": matching_event.get("summary") or event_record["summary"],
                        "category": matching_event.get("category") or event_record["category"],
                    }
                )
                conn.execute(
                    """
                    UPDATE events
                    SET title = ?, summary = ?, category = ?, country = COALESCE(?, country), country_code = COALESCE(?, country_code), latitude = COALESCE(?, latitude), longitude = COALESCE(?, longitude), importance = ?, confidence = ?, event_time = COALESCE(?, event_time)
                    WHERE id = ?
                    """,
                    (
                        event_record["title"],
                        event_record["summary"],
                        event_record["category"],
                        event_record["country"],
                        event_record["country_code"],
                        event_record["latitude"],
                        event_record["longitude"],
                        max(1, min(10, int(event_record["importance"]))),
                        max(0.0, min(1.0, float(event_record["confidence"]))),
                        event_record["event_time"],
                        event_id,
                    ),
                )
                _update_event_statistics(conn, event_id)
                existing_events = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT id, title, summary, category, country, country_code, latitude, longitude, importance, confidence, event_time, article_count, source_count FROM events"
                    ).fetchall()
                ]
                continue

            event_id = conn.execute(
                """
                INSERT INTO events (
                    title, summary, category, country, country_code, latitude, longitude,
                    importance, confidence, article_count, source_count, unique_source_count,
                    corroboration_level, first_seen_at, last_seen_at, source_domains, event_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 'single', ?, ?, ?, ?)
                """,
                (
                    event_record["title"],
                    event_record["summary"],
                    event_record["category"],
                    event_record["country"],
                    event_record["country_code"],
                    event_record["latitude"],
                    event_record["longitude"],
                    max(1, min(10, int(event_record["importance"]))),
                    max(0.0, min(1.0, float(event_record["confidence"]))),
                    event_record["event_time"],
                    event_record["event_time"],
                    ", ".join([(article.get("source") or "Unknown").strip()])
                    if (article.get("source") or "Unknown").strip()
                    else "",
                    event_record["event_time"],
                ),
            ).lastrowid
            events_created += 1
            _merge_article_to_event(conn, event_id, article_id)
            existing_events = [
                dict(row)
                for row in conn.execute(
                    "SELECT id, title, summary, category, country, country_code, latitude, longitude, importance, confidence, event_time, article_count, source_count FROM events"
                ).fetchall()
            ]

        _schedule_rag_indexing()
        return {
            "articles_seen": len(articles),
            "articles_inserted": inserted,
            "duplicates_removed": duplicates_removed,
            "events_created": events_created,
            "ai_analyzed": ai_analyzed,
            "ai_failed": ai_failed,
        }
