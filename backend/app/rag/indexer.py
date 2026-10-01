"""Incremental indexing service for the RAG search index.

The indexer turns events (and their linked articles) into searchable documents,
embeds them and stores the vectors in the configured vector store. It is
designed to be:

* **incremental** - a document is only (re)embedded when its content hash,
  embedding model or embedding status changed;
* **fail-safe** - if Ollama or the vector store is unavailable the ingestion
  pipeline keeps working, the failure is recorded in the ledger and the next
  run retries it;
* **idempotent** - running it repeatedly produces the same index state.

SQLite remains the source of truth: the ``rag_documents`` ledger is only a
derived search index and can always be rebuilt from ``events``/``articles``.
"""

import asyncio
import inspect
import logging
from datetime import datetime, timezone

from ..config import Settings, settings as global_settings
from ..database.db import get_connection
from .documents import existing_article_ids, existing_event_ids, fetch_index_documents
from .embeddings import EmbeddingError, build_embedding_provider
from .models import IndexDocument, IndexResult, VectorRecord
from .schema import ensure_rag_schema
from .timestamps import to_epoch
from .vector_store import VectorStore, VectorStoreUnavailable, get_vector_store

logger = logging.getLogger(__name__)

INDEXED = "indexed"
FAILED = "failed"
MAX_REPORTED_ERRORS = 5
SQL_CHUNK = 400

# Indexing runs in the background (startup, after ingestion, before a query).
# Without a single-flight guard those runs overlap, each embedding the same
# documents and starving the Ollama server that also serves the assistant chat.
_INDEX_LOCK = asyncio.Lock()


def indexing_in_progress() -> bool:
    """True while a background indexing run holds the lock."""
    return _INDEX_LOCK.locked()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_ts(document: IndexDocument) -> float | None:
    return to_epoch(document.event_time) or to_epoch(document.published_at)


def build_payload(document: IndexDocument) -> dict:
    """Vector payload used by the Qdrant backend and by diagnostics."""
    return {
        "document_type": document.document_type,
        "event_id": document.event_id,
        "article_id": document.article_id,
        "country": document.country,
        "country_code": document.country_code,
        "category": document.category,
        "importance": document.importance,
        "confidence": document.confidence,
        "source": document.source,
        "url": document.url,
        "published_at": document.published_at,
        "event_time": document.event_time,
        "event_ts": _event_ts(document),
        "title": document.title,
    }


def _ledger_state(conn, document_ids: list[str]) -> dict[str, tuple[str, str, str]]:
    if not document_ids:
        return {}

    state: dict[str, tuple[str, str, str]] = {}
    ids = list(document_ids)

    for start in range(0, len(ids), SQL_CHUNK):
        chunk = ids[start : start + SQL_CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT id, document_hash, embedding_model, status "
            f"FROM rag_documents WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()

        for row in rows:
            state[row["id"]] = (
                row["document_hash"] or "",
                row["embedding_model"] or "",
                row["status"] or "",
            )

    return state


async def _embed(provider, texts: list[str]):
    """Call the provider (sync or async) and return the vectors."""
    result = provider.embed(texts)
    if inspect.isawaitable(result):
        return await result
    return result


def _error_message(exc: Exception) -> str:
    if isinstance(exc, EmbeddingError):
        return str(exc)
    if isinstance(exc, VectorStoreUnavailable):
        return f"Vector store unavailable: {exc}"
    return f"{type(exc).__name__}: {exc}"


def _remember_error(errors: list[str], message: str) -> None:
    if message not in errors and len(errors) < MAX_REPORTED_ERRORS:
        errors.append(message)


def _provider_model(config: Settings) -> str | None:
    try:
        return build_embedding_provider(config).model
    except Exception:
        return None


def write_ledger_rows(
    conn,
    documents: list[IndexDocument],
    embedding_model: str,
    status: str = INDEXED,
    error: str | None = None,
    embedding_dim: int | None = None,
) -> None:
    """Insert/update ledger rows (the embedding blob is written by the store)."""
    timestamp = _now()

    for document in documents:
        conn.execute(
            """
            INSERT INTO rag_documents (
                id, document_type, event_id, article_id, title, text, country,
                country_code, category, importance, confidence, source, url,
                published_at, event_time, event_ts, document_hash,
                embedding_model, embedding_dim, status, error, indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                document_type = excluded.document_type,
                event_id = excluded.event_id,
                article_id = excluded.article_id,
                title = excluded.title,
                text = excluded.text,
                country = excluded.country,
                country_code = excluded.country_code,
                category = excluded.category,
                importance = excluded.importance,
                confidence = excluded.confidence,
                source = excluded.source,
                url = excluded.url,
                published_at = excluded.published_at,
                event_time = excluded.event_time,
                event_ts = excluded.event_ts,
                document_hash = excluded.document_hash,
                embedding_model = excluded.embedding_model,
                embedding_dim = COALESCE(
                    excluded.embedding_dim, rag_documents.embedding_dim
                ),
                status = excluded.status,
                error = excluded.error,
                indexed_at = excluded.indexed_at
            """,
            (
                document.id,
                document.document_type,
                document.event_id,
                document.article_id,
                document.title,
                document.text,
                document.country,
                document.country_code,
                document.category,
                document.importance,
                document.confidence,
                document.source,
                document.url,
                document.published_at,
                document.event_time,
                _event_ts(document),
                document.document_hash,
                embedding_model,
                embedding_dim,
                status,
                error,
                timestamp,
            ),
        )

    conn.commit()


async def index_documents(
    documents: list[IndexDocument],
    conn=None,
    provider=None,
    store: VectorStore | None = None,
    config: Settings | None = None,
    force: bool = False,
) -> IndexResult:
    """Embed and store the given documents, skipping unchanged ones."""
    config = config or global_settings
    provider = provider or build_embedding_provider(config)
    owns_conn = conn is None

    if owns_conn:
        conn = get_connection()

    try:
        ensure_rag_schema(conn)

        if not documents:
            return IndexResult(
                status="ok",
                embedding_model=provider.model,
                vector_store=getattr(store, "name", None),
            )

        if store is None:
            store = get_vector_store(config)

        state = _ledger_state(conn, [document.id for document in documents])
        pending: list[IndexDocument] = []
        skipped = 0

        for document in documents:
            previous_hash, previous_model, previous_status = state.get(
                document.id, ("", "", "")
            )
            unchanged = (
                previous_hash == document.document_hash
                and previous_model == provider.model
                and previous_status == INDEXED
            )

            if unchanged and not force:
                skipped += 1
                continue

            pending.append(document)

        if not pending:
            return IndexResult(
                status="ok",
                scanned=len(documents),
                skipped=skipped,
                embedding_model=provider.model,
                vector_store=getattr(store, "name", None),
            )

        batch_size = max(1, int(config.rag_embedding_batch_size))
        indexed = 0
        failed = 0
        errors: list[str] = []

        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]

            # Yield between batches: embedding is I/O bound, but the SQLite reads
            # and writes around it are synchronous, so without this the event loop
            # stalls and every HTTP request queues behind indexing.
            await asyncio.sleep(0)

            try:
                vectors = await _embed(provider, [document.text for document in batch])
            except Exception as exc:
                failed += len(batch)
                message = _error_message(exc)
                _remember_error(errors, message)
                write_ledger_rows(conn, batch, provider.model, status=FAILED, error=message)
                logger.warning(
                    "[RAG] Embedding failed for %s document(s): %s", len(batch), message
                )
                continue

            write_ledger_rows(
                conn,
                batch,
                provider.model,
                status=INDEXED,
                embedding_dim=len(vectors[0]) if vectors else None,
            )

            try:
                store.upsert(
                    [
                        VectorRecord(
                            id=document.id,
                            vector=vector,
                            payload=build_payload(document),
                        )
                        for document, vector in zip(batch, vectors)
                    ]
                )
            except Exception as exc:
                failed += len(batch)
                message = _error_message(exc)
                _remember_error(errors, message)
                write_ledger_rows(conn, batch, provider.model, status=FAILED, error=message)
                logger.warning("[RAG] Vector upsert failed: %s", message)
                continue

            indexed += len(batch)

        status = "ok"
        if failed and indexed:
            status = "partial"
        elif failed and not indexed:
            status = "unavailable"

        return IndexResult(
            status=status,
            scanned=len(documents),
            indexed=indexed,
            skipped=skipped,
            failed=failed,
            embedding_model=provider.model,
            vector_store=getattr(store, "name", None),
            errors=errors,
            message=(
                "Indexing incomplete: the embedding or vector store service is "
                "unavailable. Ingestion and the rest of the platform keep working; "
                "the index retries on the next run."
                if failed
                else None
            ),
        )
    finally:
        if owns_conn and conn is not None:
            conn.close()


async def index_pending(
    limit: int | None = None,
    force: bool = False,
    conn=None,
    provider=None,
    store: VectorStore | None = None,
    config: Settings | None = None,
    event_ids: list[int] | None = None,
) -> IndexResult:
    """Index new/changed events (and linked articles) and prune removed ones.

    This is the entry point used by ingestion, by the API and by the optional
    startup task. It never raises for infrastructure problems: failures are
    reported in the returned :class:`IndexResult` so ingestion continues.
    """
    config = config or global_settings
    owns_conn = conn is None

    if owns_conn:
        conn = get_connection()

    try:
        ensure_rag_schema(conn)

        try:
            provider = provider or build_embedding_provider(config)
        except Exception as exc:
            return IndexResult(
                status="unavailable",
                message=f"Embedding provider is not configured: {_error_message(exc)}",
                errors=[_error_message(exc)],
            )

        try:
            store = store or get_vector_store(config)
        except VectorStoreUnavailable as exc:
            return IndexResult(
                status="unavailable",
                message=f"Vector store unavailable: {exc}",
                embedding_model=provider.model,
                errors=[str(exc)],
            )

        documents = fetch_index_documents(
            conn,
            event_ids=event_ids,
            limit=limit if event_ids is None else None,
        )

        result = await index_documents(
            documents,
            conn=conn,
            provider=provider,
            store=store,
            config=config,
            force=force,
        )

        result.pruned = prune_orphans(conn=conn, store=store, config=config)
        return result
    except Exception as exc:  # never break the caller (ingestion)
        logger.exception("[RAG] Indexing run failed")
        return IndexResult(
            status="unavailable",
            message=_error_message(exc),
            errors=[_error_message(exc)],
        )
    finally:
        if owns_conn and conn is not None:
            conn.close()


def prune_orphans(conn=None, store: VectorStore | None = None, config=None) -> int:
    """Remove index entries whose event/article no longer exists in SQLite."""
    config = config or global_settings
    owns_conn = conn is None

    if owns_conn:
        conn = get_connection()

    try:
        ensure_rag_schema(conn)
        rows = conn.execute(
            "SELECT id, document_type, event_id, article_id FROM rag_documents"
        ).fetchall()

        if not rows:
            return 0

        event_ids = sorted({int(row["event_id"]) for row in rows if row["event_id"]})
        article_ids = sorted(
            {int(row["article_id"]) for row in rows if row["article_id"]}
        )
        live_events = existing_event_ids(conn, event_ids)
        live_articles = existing_article_ids(conn, article_ids)

        stale: list[str] = []
        for row in rows:
            if row["document_type"] == "event" and row["event_id"]:
                if int(row["event_id"]) not in live_events:
                    stale.append(row["id"])
            elif row["document_type"] == "article" and row["article_id"]:
                if int(row["article_id"]) not in live_articles:
                    stale.append(row["id"])

        if not stale:
            return 0

        for start in range(0, len(stale), SQL_CHUNK):
            chunk = stale[start : start + SQL_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(
                f"DELETE FROM rag_documents WHERE id IN ({placeholders})", chunk
            )
        conn.commit()

        if store is not None:
            try:
                store.delete(stale)
            except Exception as exc:
                logger.warning("[RAG] Could not delete stale vectors: %s", exc)

        return len(stale)
    finally:
        if owns_conn and conn is not None:
            conn.close()


def delete_event_documents(conn, event_ids: list[int]) -> int:
    """Drop index entries for specific events (used when events are purged)."""
    if not event_ids:
        return 0

    ensure_rag_schema(conn)
    ids = [int(event_id) for event_id in event_ids]
    removed = 0

    for start in range(0, len(ids), SQL_CHUNK):
        chunk = ids[start : start + SQL_CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        cursor = conn.execute(
            f"DELETE FROM rag_documents WHERE event_id IN ({placeholders})", chunk
        )
        removed += cursor.rowcount or 0

    conn.commit()
    return removed


def index_stats(conn=None, config: Settings | None = None) -> dict:
    """Return index coverage information for the status endpoint."""
    config = config or global_settings
    owns_conn = conn is None

    if owns_conn:
        conn = get_connection()

    try:
        ensure_rag_schema(conn)
        model = _provider_model(config)

        def scalar(sql: str, params=()) -> int:
            row = conn.execute(sql, params).fetchone()
            return int(row[0] if row and row[0] is not None else 0)

        indexed_documents = scalar(
            "SELECT COUNT(*) FROM rag_documents WHERE status = ?", (INDEXED,)
        )
        failed_documents = scalar(
            "SELECT COUNT(*) FROM rag_documents WHERE status = ?", (FAILED,)
        )
        vector_documents = scalar(
            "SELECT COUNT(*) FROM rag_documents WHERE embedding IS NOT NULL"
        )

        if model:
            indexed_events = scalar(
                "SELECT COUNT(*) FROM rag_documents "
                "WHERE document_type = 'event' AND status = ? AND embedding_model = ?",
                (INDEXED, model),
            )
            indexed_articles = scalar(
                "SELECT COUNT(*) FROM rag_documents "
                "WHERE document_type = 'article' AND status = ? AND embedding_model = ?",
                (INDEXED, model),
            )
        else:
            indexed_events = scalar(
                "SELECT COUNT(*) FROM rag_documents WHERE document_type = 'event'"
            )
            indexed_articles = scalar(
                "SELECT COUNT(*) FROM rag_documents WHERE document_type = 'article'"
            )

        total_events = scalar("SELECT COUNT(*) FROM events")
        total_articles = scalar("SELECT COUNT(*) FROM event_articles")
        last_indexed_at_row = conn.execute(
            "SELECT MAX(indexed_at) FROM rag_documents WHERE status = ?", (INDEXED,)
        ).fetchone()

        pending = max(0, total_events - indexed_events) + max(
            0, total_articles - indexed_articles
        )

        return {
            "indexed_documents": indexed_documents,
            "indexed_events": indexed_events,
            "indexed_articles": indexed_articles,
            "failed_documents": failed_documents,
            "vector_documents": vector_documents,
            "total_events": total_events,
            "total_articles": total_articles,
            "pending_documents": pending,
            "embedding_model": model,
            "last_indexed_at": last_indexed_at_row[0] if last_indexed_at_row else None,
        }
    finally:
        if owns_conn and conn is not None:
            conn.close()


async def index_after_ingestion(limit: int | None = None, config=None) -> IndexResult | None:
    """Hook used by the ingestion pipeline: index new events, never raise.

    A news cycle only creates a handful of events, so this deliberately uses a
    small batch: re-reading and re-embedding hundreds of documents after every
    collection run competed with the ingestion's own model calls and made the
    whole backend feel slow. Anything left over is picked up later by the
    startup run or by ``POST /api/ai/index``.
    """
    config = config or global_settings

    if not config.rag_enabled:
        return None

    if _INDEX_LOCK.locked():
        logger.info("[RAG] Skipping post-ingestion indexing: a run is already active")
        return None

    try:
        async with _INDEX_LOCK:
            return await index_pending(
                limit=limit or config.rag_ingestion_index_limit,
                config=config,
            )
    except Exception as exc:  # defensive: ingestion must always complete
        logger.warning("[RAG] Post-ingestion indexing failed: %s", exc)
        return None




