"""Hybrid retrieval over the SQLite search index (+ optional vectors).

Retrieval is deterministic where it can be: structured constraints from the
query plan (country/category/date/importance) are pushed into SQL filters, the
lexical pass scores the indexed document text, and when an embedding provider
and vector store are reachable the vector pass adds semantic matches. Scores
from both passes are normalised and combined with the configured weights.

Every candidate is then re-hydrated from SQLite (the source of truth): stale
index entries whose event/article no longer exists are dropped, and sources are
always taken from live ``articles`` rows, never from the index or the model.
"""

import logging
from datetime import datetime, timezone

from ..config import Settings, settings as global_settings
from ..database.db import get_connection
from .documents import fetch_linked_articles
from .embeddings import EmbeddingError, build_embedding_provider
from .models import (
    EvidenceRecord,
    QueryPlan,
    RetrievalDiagnostics,
    SourceCitation,
)
from .schema import ensure_rag_schema
from .timestamps import to_epoch, to_iso
from .vector_store import VectorStoreUnavailable, build_sql_filters, get_vector_store

logger = logging.getLogger(__name__)

STRONG_RELEVANCE = 0.62
MODERATE_RELEVANCE = 0.38
LIMITED_RELEVANCE = 0.15

# Cap for questions that carry no keywords ("what happened recently?"). These
# records are returned because they match the filters, not because they match
# the wording, so they must never look like a strong match.
RECENCY_FALLBACK_RELEVANCE = 0.3


def _lexical_score(text: str, keywords: list[str]) -> float:
    if not keywords or not text:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in lowered)
    if not hits:
        return 0.0
    extra = sum(min(3, lowered.count(kw.lower())) * 0.05 for kw in keywords)
    return (hits / max(1, len(keywords))) + min(0.5, extra)


def _filters_for_plan(plan: QueryPlan) -> dict:
    filters = plan.filters
    return {
        "country_codes": list(filters.country_codes or []),
        "categories": list(filters.categories or []),
        "min_importance": filters.min_importance,
        "date_from_ts": to_epoch(filters.date_from) if filters.date_from else None,
        "date_to_ts": to_epoch(filters.date_to) if filters.date_to else None,
    }


def _norm(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    peak = max(values.values()) or 1.0
    if peak <= 0:
        return {key: 0.0 for key in values}
    return {key: value / peak for key, value in values.items()}


def relevance_label(score: float) -> str:
    if score >= STRONG_RELEVANCE:
        return "strong"
    if score >= MODERATE_RELEVANCE:
        return "moderate"
    if score >= LIMITED_RELEVANCE:
        return "limited"
    return "none"


async def _embed_query(question: str, config: Settings) -> list[float] | None:
    """Embed the question; ``None`` means the vector pass is skipped."""
    try:
        provider = build_embedding_provider(config)
    except EmbeddingError as exc:
        logger.info("[RAG] Embedding provider unavailable: %s", exc)
        return None

    try:
        vectors = await provider.embed([question])
    except Exception as exc:  # noqa: BLE001 - degrade, never fail the request
        logger.info("[RAG] Query embedding failed: %s", exc)
        return None

    return vectors[0] if vectors else None


def _lexical_candidates(
    conn,
    plan: QueryPlan,
    keywords: list[str],
    config: Settings,
) -> tuple[list[dict], int]:
    """Rows matching the structured filters, scored lexically."""
    filters = _filters_for_plan(plan)
    where, params = build_sql_filters(filters)
    sql = (
        "SELECT id, document_type, event_id, article_id, title, text, country, "
        "country_code, category, importance, confidence, source, url, "
        "published_at, event_time, event_ts "
        "FROM rag_documents WHERE status = 'indexed'"
    )
    if where:
        sql += f" AND {where}"
    sql += " ORDER BY COALESCE(event_ts, 0) DESC LIMIT ?"
    params.append(max(1, int(config.rag_candidate_pool)))

    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    scanned = len(rows)

    for row in rows:
        row["_lexical"] = _lexical_score(
            f"{row.get('title') or ''}\n{row.get('text') or ''}", keywords
        )

    # Keep rows the lexical pass likes. When the question carried no usable
    # keywords at all ("what happened recently?"), fall back to the most recent
    # rows so filter-only questions still return evidence. Keyword questions
    # with zero hits must stay empty instead of matching unrelated records.
    scored = [row for row in rows if row["_lexical"] > 0]
    if not scored and not keywords and plan.question_type in {
        "latest", "aggregate", "importance", "historical",
    }:
        scored = rows[: max(1, int(config.rag_top_k))]
        # Mark them so the caller can report honest, capped relevance instead of
        # letting the normalisation turn a recency fallback into a "strong" hit.
        for position, row in enumerate(scored):
            row["_recency_fallback"] = True
            row["_lexical"] = 1.0 / (1 + position)

    return scored, scanned


async def _vector_candidates(
    plan: QueryPlan,
    config: Settings,
) -> tuple[list[dict], object | None, str | None]:
    """Rows matching the structured filters, scored by vector similarity."""
    filters = _filters_for_plan(plan)
    vector = await _embed_query(plan.question, config)
    if not vector:
        return [], None, "query embedding unavailable"

    try:
        store = get_vector_store(config)
    except VectorStoreUnavailable as exc:
        return [], None, str(exc)

    try:
        hits = store.search(
            vector,
            limit=max(1, int(config.rag_top_k)) * 3,
            filters=filters,
        )
    except Exception as exc:  # noqa: BLE001 - Qdrant may disappear mid-request
        logger.info("[RAG] Vector search failed: %s", exc)
        store.close()
        return [], None, f"vector search failed: {exc}"

    rows = [{"id": hit.id, "_vector": hit.score} for hit in hits]
    return rows, store, None


def _load_documents(conn, document_ids: list[str]) -> dict[str, dict]:
    if not document_ids:
        return {}
    loaded: dict[str, dict] = {}
    for start in range(0, len(document_ids), 400):
        chunk = document_ids[start : start + 400]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT id, document_type, event_id, article_id, title, text, country, "
            "country_code, category, importance, confidence, source, url, "
            "published_at, event_time, event_ts "
            f"FROM rag_documents WHERE id IN ({placeholders}) AND status = 'indexed'",
            chunk,
        ).fetchall()
        for row in rows:
            loaded[row["id"]] = dict(row)
    return loaded


def _renumber(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    """Reassign record numbers 1..N and keep source citations in sync."""
    for index, record in enumerate(records, start=1):
        record.record_number = index
        for source in record.sources:
            source.record_number = index
    return records


def _order_for_question_type(
    records: list[EvidenceRecord], plan: QueryPlan
) -> list[EvidenceRecord]:
    """Re-rank evidence for question intents that are not pure relevance.

    ``sources`` questions ask for the best corroborated events and
    ``importance`` questions for the highest scored ones, so relevance alone is
    not the right ordering for them.
    """
    if plan.question_type == "sources":
        return _renumber(
            sorted(
                records,
                key=lambda record: (
                    record.source_count or 0,
                    record.article_count or 0,
                    record.relevance,
                ),
                reverse=True,
            )
        )

    if plan.question_type == "importance":
        return _renumber(
            sorted(
                records,
                key=lambda record: (record.importance or 0, record.relevance),
                reverse=True,
            )
        )

    return records


def _event_evidence(
    conn, row: dict, record_number: int, relevance: float, matched_on: str
) -> EvidenceRecord | None:
    """Rehydrate an event document from the live ``events`` table."""
    event = conn.execute(
        "SELECT id, title, summary, category, country, country_code, importance, "
        "confidence, article_count, source_count, unique_source_count, "
        "corroboration_level, source_domains, event_time "
        "FROM events WHERE id = ?",
        (row.get("event_id"),),
    ).fetchone()
    if event is None:
        return None  # stale index entry: source of truth says it is gone

    linked = fetch_linked_articles(conn, [int(event["id"])])
    articles = linked.get(int(event["id"]), [])

    sources = [
        SourceCitation(
            index=index,
            document_type="event",
            event_id=int(event["id"]),
            article_id=int(article.get("id")),
            title=article.get("title"),
            source=article.get("source"),
            url=article.get("url"),
            published_at=article.get("published_at"),
            verified_in_database=True,
            record_number=record_number,
        )
        for index, article in enumerate(articles[:6], start=1)
    ]

    domains = [
        domain.strip()
        for domain in (event["source_domains"] or "").split(",")
        if domain.strip()
    ]

    return EvidenceRecord(
        record_number=record_number,
        document_type="event",
        event_id=int(event["id"]),
        title=event["title"],
        summary=event["summary"] or "",
        category=event["category"],
        country=event["country"],
        country_code=event["country_code"],
        importance=event["importance"],
        confidence=event["confidence"],
        corroboration_level=event["corroboration_level"],
        article_count=event["article_count"],
        source_count=event["source_count"],
        source_domains=domains,
        event_time=to_iso(event["event_time"]) or event["event_time"],
        relevance=round(relevance, 4),
        matched_on=matched_on,
        sources=sources,
    )


def _article_evidence(
    conn, row: dict, record_number: int, relevance: float, matched_on: str
) -> EvidenceRecord | None:
    """Rehydrate an article document from the live ``articles`` table."""
    article = conn.execute(
        "SELECT id, title, url, source, published_at, description "
        "FROM articles WHERE id = ?",
        (row.get("article_id"),),
    ).fetchone()
    if article is None:
        return None  # stale index entry

    event_row = None
    if row.get("event_id") is not None:
        event_row = conn.execute(
            "SELECT id, title, category, country, country_code, importance, "
            "confidence, corroboration_level, source_domains, event_time "
            "FROM events WHERE id = ?",
            (row.get("event_id"),),
        ).fetchone()

    source = SourceCitation(
        index=1,
        document_type="article",
        event_id=row.get("event_id"),
        article_id=int(article["id"]),
        title=article["title"],
        source=article["source"],
        url=article["url"],
        published_at=article["published_at"],
        verified_in_database=True,
        record_number=record_number,
    )

    domains = []
    if event_row is not None:
        domains = [
            domain.strip()
            for domain in (event_row["source_domains"] or "").split(",")
            if domain.strip()
        ]

    return EvidenceRecord(
        record_number=record_number,
        document_type="article",
        event_id=row.get("event_id"),
        title=article["title"],
        summary=article["description"] or "",
        category=(event_row["category"] if event_row else None) or row.get("category"),
        country=(event_row["country"] if event_row else None) or row.get("country"),
        country_code=(
            (event_row["country_code"] if event_row else None) or row.get("country_code")
        ),
        importance=(event_row["importance"] if event_row else None) or row.get("importance"),
        confidence=(event_row["confidence"] if event_row else None) or row.get("confidence"),
        corroboration_level=event_row["corroboration_level"] if event_row else None,
        source_domains=domains,
        event_time=to_iso(article["published_at"]) or article["published_at"],
        published_at=to_iso(article["published_at"]) or article["published_at"],
        relevance=round(relevance, 4),
        matched_on=matched_on,
        sources=[source],
    )
async def retrieve(
    plan: QueryPlan,
    config: Settings | None = None,
) -> tuple[list[EvidenceRecord], RetrievalDiagnostics]:
    """Run hybrid retrieval for ``plan``.

    Returns the evidence records (record numbers assigned 1..N, capped at
    ``rag_max_context_documents``) plus diagnostics for the API/UI. Infrastructure
    problems never raise: they are reported through the diagnostics so the
    service layer can answer with whatever evidence is available.
    """
    config = config or global_settings
    started = datetime.now(timezone.utc)

    diagnostics = RetrievalDiagnostics(
        filters_applied=_filters_for_plan(plan),
        notes=[],
    )

    conn = get_connection()
    store = None
    try:
        try:
            ensure_rag_schema(conn)
        except Exception as exc:  # noqa: BLE001
            diagnostics.notes.append(f"RAG schema unavailable: {exc}")
            diagnostics.mode = "none"
            return [], diagnostics

        indexed = conn.execute(
            "SELECT COUNT(*) FROM rag_documents WHERE status = 'indexed'"
        ).fetchone()[0]
        diagnostics.documents_indexed = int(indexed or 0)

        # Only the plan knows which words are question words, filter values or
        # genuinely searchable terms, so never re-derive keywords here: an empty
        # list means "this question is filter-only", which the recency fallback
        # in ``_lexical_candidates`` handles.
        keywords = list(plan.filters.keywords or [])
        lexical_rows, scanned = _lexical_candidates(conn, plan, keywords, config)

        vector_rows, store, vector_note = await _vector_candidates(plan, config)
        if vector_note:
            diagnostics.notes.append(vector_note)
        if store is not None:
            diagnostics.vector_store = store.name
            diagnostics.vector_store_detail = store.detail
            diagnostics.vector_search_available = bool(store.available)
        else:
            diagnostics.vector_search_available = False

        diagnostics.candidates_scanned = scanned

        lexical_scores = _norm(
            {row["id"]: float(row.get("_lexical") or 0.0) for row in lexical_rows}
        )
        vector_scores = _norm(
            {row["id"]: float(row.get("_vector") or 0.0) for row in vector_rows}
        )

        if lexical_scores and vector_scores:
            diagnostics.mode = "hybrid"
        elif vector_scores:
            diagnostics.mode = "vector"
        elif lexical_scores:
            diagnostics.mode = "lexical"
        else:
            diagnostics.mode = "none"

        if diagnostics.mode == "none":
            diagnostics.notes.append(
                "No indexed records matched the question and filters."
            )
            return [], diagnostics

        recency_fallback = {
            row["id"] for row in lexical_rows if row.get("_recency_fallback")
        }

        all_ids = set(lexical_scores) | set(vector_scores)
        documents = _load_documents(conn, list(all_ids))

        combined: list[tuple[str, float, str]] = []
        for document_id in all_ids:
            row = documents.get(document_id)
            if row is None:
                continue  # stale or filtered out
            lex = lexical_scores.get(document_id, 0.0)
            vec = vector_scores.get(document_id, 0.0)
            if lexical_scores and vector_scores:
                score = config.rag_vector_weight * vec + config.rag_lexical_weight * lex
                matched_on = (
                    "vector+lexical" if lex and vec else ("vector" if vec else "lexical")
                )
            elif vector_scores:
                score = vec
                matched_on = "vector"
            else:
                score = lex
                matched_on = "lexical"

            if document_id in recency_fallback and not vec:
                score = min(score, RECENCY_FALLBACK_RELEVANCE)
                matched_on = "recency"

            if score >= config.rag_min_relevance:
                combined.append((document_id, score, matched_on))

        if not combined:
            diagnostics.notes.append(
                "Candidates found but none cleared the minimum relevance threshold."
            )
            diagnostics.mode = "none"
            return [], diagnostics

        combined.sort(key=lambda item: item[1], reverse=True)
        limit = max(1, int(config.rag_max_context_documents))
        combined = combined[:limit]

        evidence: list[EvidenceRecord] = []
        record_number = 0
        for document_id, score, matched_on in combined:
            row = documents[document_id]
            record_number += 1
            if row["document_type"] == "article":
                record = _article_evidence(conn, row, record_number, score, matched_on)
            else:
                record = _event_evidence(conn, row, record_number, score, matched_on)
            if record is not None:
                evidence.append(record)
            else:
                record_number -= 1  # stale index entry dropped

        evidence = _order_for_question_type(evidence, plan)

        top_score = evidence[0].relevance if evidence else 0.0
        diagnostics.top_score = round(top_score, 4)
        diagnostics.relevance = relevance_label(top_score)
        diagnostics.vector_store = diagnostics.vector_store or "sqlite"
        diagnostics.filters_applied = _filters_for_plan(plan)
        diagnostics.notes.append(
            f"retrieved {len(evidence)} record(s) in "
            f"{(datetime.now(timezone.utc) - started).total_seconds():.2f}s"
        )

        if not evidence:
            diagnostics.mode = "none"
            diagnostics.notes.append(
                "All matched index entries were stale relative to the database."
            )

        return evidence, diagnostics
    finally:
        if store is not None:
            store.close()
        conn.close()



