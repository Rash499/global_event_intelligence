"""Build the searchable documents that feed the RAG index.

Everything here is derived from the platform's SQLite database, which stays the
source of truth. Two document types are produced:

``event``
    One document per event. Contains the Phase 1 intelligence fields
    (category, country, importance, confidence, corroboration, timing) plus the
    titles of the reporting articles.

``article``
    One document per article that is linked to an event. Contains the article
    metadata (title, description, publisher, URL, publish time) plus a copy of
    the parent event's structured metadata so filtered retrieval can be applied
    to article documents as well.
"""

import hashlib
import json
from typing import Any

from .models import IndexDocument

RAG_DOCUMENT_SCHEMA_VERSION = "v1"
MAX_ARTICLES_PER_EVENT = 12
MAX_EVENT_TEXT_CHARACTERS = 2000


def event_document_id(event_id: int | str) -> str:
    return f"event:{int(event_id)}"


def article_document_id(article_id: int | str) -> str:
    return f"article:{int(article_id)}"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _format_importance(value: Any) -> str:
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "unknown"


def _format_confidence(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "unknown"


def hash_document(*parts: Any) -> str:
    """Stable hash used to detect new/changed documents for incremental indexing."""
    payload = json.dumps([str(part) for part in parts], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_header(row: dict) -> str:
    country = _clean(row.get("country")) or "unknown"
    country_code = _clean(row.get("country_code")) or "n/a"
    location = ""
    if row.get("latitude") is not None and row.get("longitude") is not None:
        try:
            location = f"{float(row['latitude']):.4f}, {float(row['longitude']):.4f}"
        except (TypeError, ValueError):
            location = ""

    lines = [
        f"EVENT {row.get('id')}",
        f"Title: {_clean(row.get('title'))}",
        f"Category: {_clean(row.get('category')) or 'unknown'}",
        f"Country: {country} ({country_code})",
    ]

    if location:
        lines.append(f"Coordinates: {location}")

    lines.extend(
        [
            "Importance score (platform-derived, 1-10): "
            f"{_format_importance(row.get('importance'))}",
            "Event confidence (platform-derived, 0-1): "
            f"{_format_confidence(row.get('confidence'))}",
            "Reporting volume: "
            f"{int(row.get('article_count') or 0)} articles from "
            f"{int(row.get('unique_source_count') or row.get('source_count') or 0)} "
            "independent sources; "
            f"corroboration: {_clean(row.get('corroboration_level')) or 'unknown'}",
            f"Event time: {_clean(row.get('event_time')) or 'unknown'}",
            f"First seen: {_clean(row.get('first_seen_at')) or 'unknown'}",
            f"Last seen: {_clean(row.get('last_seen_at')) or 'unknown'}",
        ]
    )

    domains = _clean(row.get("source_domains"))
    if domains:
        lines.append(f"Reporting domains: {domains}")

    return "\n".join(lines)


def build_event_document(row: dict, articles: list[dict] | None = None) -> IndexDocument:
    """Build the searchable document for a single event."""
    articles = articles or []
    summary = _clean(row.get("summary"))
    parts = [_event_header(row)]

    if summary:
        parts.append(f"Summary: {summary}")

    if articles:
        lines = ["Linked reporting:"]
        for article in articles[:MAX_ARTICLES_PER_EVENT]:
            title = _clean(article.get("title")) or "Untitled article"
            publisher = _clean(article.get("source")) or "unknown publisher"
            published = _clean(article.get("published_at"))
            published_part = f", {published}" if published else ""
            lines.append(f"- [A{article.get('id')}] {title} ({publisher}{published_part})")
        parts.append("\n".join(lines))

    text = _truncate("\n".join(parts), MAX_EVENT_TEXT_CHARACTERS)

    document = IndexDocument(
        id=event_document_id(row["id"]),
        document_type="event",
        event_id=int(row["id"]),
        title=_clean(row.get("title")) or "Untitled event",
        text=text,
        document_hash="",
        country=_clean(row.get("country")) or None,
        country_code=_clean(row.get("country_code")) or None,
        category=_clean(row.get("category")) or None,
        importance=int(row["importance"]) if row.get("importance") is not None else None,
        confidence=(
            float(row["confidence"]) if row.get("confidence") is not None else None
        ),
        event_time=_clean(row.get("event_time")) or _clean(row.get("created_at")) or None,
    )

    document.document_hash = hash_document(
        RAG_DOCUMENT_SCHEMA_VERSION,
        document.text,
        document.country_code,
        document.category,
        document.importance,
        document.title,
        [article.get("id") for article in articles],
    )

    return document


def build_article_document(article: dict, event_row: dict | None = None) -> IndexDocument:
    """Build the searchable document for an article linked to an event."""
    event_row = event_row or {}
    title = _clean(article.get("title")) or "Untitled article"
    publisher = _clean(article.get("source")) or "unknown publisher"
    url = _clean(article.get("url"))
    published = _clean(article.get("published_at"))
    description = _truncate(_clean(article.get("description")), 900)

    lines = [
        f"ARTICLE {article.get('id')} (linked to event {event_row.get('id')})",
        f"Title: {title}",
        f"Publisher: {publisher}",
        f"Published: {published or 'unknown'}",
        f"URL: {url or 'unknown'}",
    ]

    if description:
        lines.append(f"Description: {description}")

    if event_row:
        lines.append(
            "Parent event context: "
            f"{_clean(event_row.get('title'))} | "
            f"category={_clean(event_row.get('category')) or 'unknown'} | "
            f"country={_clean(event_row.get('country')) or 'unknown'} "
            f"({_clean(event_row.get('country_code')) or 'n/a'}) | "
            f"importance={_format_importance(event_row.get('importance'))}"
        )

    document = IndexDocument(
        id=article_document_id(article["id"]),
        document_type="article",
        event_id=int(event_row["id"]) if event_row.get("id") is not None else None,
        article_id=int(article["id"]),
        title=title,
        text="\n".join(lines),
        document_hash="",
        country=_clean(event_row.get("country")) or None,
        country_code=_clean(event_row.get("country_code")) or None,
        category=_clean(event_row.get("category")) or None,
        importance=(
            int(event_row["importance"]) if event_row.get("importance") is not None else None
        ),
        confidence=(
            float(event_row["confidence"]) if event_row.get("confidence") is not None else None
        ),
        source=publisher,
        url=url or None,
        published_at=published or None,
        event_time=_clean(event_row.get("event_time")) or None,
    )

    document.document_hash = hash_document(
        RAG_DOCUMENT_SCHEMA_VERSION,
        document.text,
        document.url,
    )

    return document


EVENT_SELECT_COLUMNS = """
    events.id, events.title, events.summary, events.category, events.country,
    events.country_code, events.latitude, events.longitude, events.importance,
    events.confidence, events.article_count, events.source_count,
    events.unique_source_count, events.corroboration_level, events.source_domains,
    events.first_seen_at, events.last_seen_at, events.event_time, events.created_at
"""

ARTICLE_SELECT_COLUMNS = "id, title, url, source, published_at, description, image_url"

SQL_PARAMETER_CHUNK = 500


def chunked(values: list, size: int = SQL_PARAMETER_CHUNK):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_linked_articles(conn, event_ids: list[int]) -> dict[int, list[dict]]:
    """Return ``{event_id: [article, ...]}`` for the requested events."""
    if not event_ids:
        return {}

    grouped: dict[int, list[dict]] = {}

    for chunk in chunked([int(event_id) for event_id in event_ids]):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT ea.event_id AS link_event_id, a.{ARTICLE_SELECT_COLUMNS.replace(", ", ", a.")}
            FROM event_articles ea
            JOIN articles a ON a.id = ea.article_id
            WHERE ea.event_id IN ({placeholders})
            ORDER BY a.published_at DESC, a.id DESC
            """,
            chunk,
        ).fetchall()

        for row in rows:
            record = dict(row)
            event_id = int(record.pop("link_event_id"))
            grouped.setdefault(event_id, []).append(record)

    return grouped


def _has_ledger(conn) -> bool:
    """True once the RAG ledger table exists (it may not on a fresh database)."""
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("rag_documents",),
        ).fetchone()
    except Exception:  # noqa: BLE001 - a missing/broken table just means no join
        return False
    return row is not None


def fetch_index_documents(
    conn,
    event_ids: list[int] | None = None,
    limit: int | None = None,
) -> list[IndexDocument]:
    """Build the full set of index documents for events (and their articles)."""
    sql = f"SELECT {EVENT_SELECT_COLUMNS} FROM events"
    params: list = []

    if event_ids:
        ids = [int(event_id) for event_id in event_ids]
        documents: list[IndexDocument] = []

        for chunk in chunked(ids):
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"{sql} WHERE id IN ({placeholders})", chunk
            ).fetchall()
            documents.extend(_build_documents(conn, [dict(row) for row in rows]))

        return documents

    # Work that is still outstanding first (never indexed, or not in the
    # ``indexed`` state), newest first within each group. Without this, a batch
    # limit would keep re-reading the same newest events and the older tail of
    # the database would never be indexed.
    if _has_ledger(conn):
        sql += (
            " LEFT JOIN rag_documents AS ledger"
            " ON ledger.id = 'event:' || events.id"
        )
        sql += (
            " ORDER BY CASE WHEN ledger.id IS NULL OR ledger.status != 'indexed'"
            " THEN 0 ELSE 1 END, events.id DESC"
        )
    else:
        sql += " ORDER BY events.id DESC"

    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))

    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    documents = _build_documents(conn, rows)

    if limit is not None and len(documents) > limit:
        # Event documents come first, so a limit of N events still bounds the
        # number of documents returned.
        documents = documents[: limit * (MAX_ARTICLES_PER_EVENT + 1)]

    return documents


def _build_documents(conn, event_rows: list[dict]) -> list[IndexDocument]:
    if not event_rows:
        return []

    grouped = fetch_linked_articles(conn, [row["id"] for row in event_rows])
    documents: list[IndexDocument] = []

    for row in event_rows:
        articles = grouped.get(int(row["id"]), [])
        documents.append(build_event_document(row, articles))
        for article in articles:
            documents.append(build_article_document(article, row))

    return documents


def existing_event_ids(conn, event_ids: list[int]) -> set[int]:
    """Subset of ``event_ids`` that still exist in the database."""
    if not event_ids:
        return set()

    found: set[int] = set()
    for chunk in chunked([int(event_id) for event_id in event_ids]):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id FROM events WHERE id IN ({placeholders})", chunk
        ).fetchall()
        found.update(int(row["id"]) for row in rows)

    return found


def existing_article_ids(conn, article_ids: list[int]) -> set[int]:
    """Subset of ``article_ids`` that still exist in the database."""
    if not article_ids:
        return set()

    found: set[int] = set()
    for chunk in chunked([int(article_id) for article_id in article_ids]):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id FROM articles WHERE id IN ({placeholders})", chunk
        ).fetchall()
        found.update(int(row["id"]) for row in rows)

    return found
