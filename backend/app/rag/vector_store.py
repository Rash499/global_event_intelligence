"""Vector store abstraction for the RAG index.

The vector database is a *derived search index*: SQLite stays the source of
truth, and every answer is re-hydrated from SQLite before it reaches the UI.

Two backends are supported:

``sqlite``
    Default, zero-dependency backend. Embeddings are stored as little-endian
    float32 blobs in the ``rag_documents`` table of the application database and
    scored with an exact dot-product scan (the local corpus is small).

``qdrant``
    Used when Qdrant is configured and reachable, either as a server
    (``QDRANT_URL``) or in embedded local mode (``QDRANT_LOCAL_PATH``).
"""

import math
import socket
import sqlite3
import struct
import threading
import time
from array import array
from concurrent.futures import ThreadPoolExecutor
from operator import mul
from typing import Protocol
from urllib.parse import urlparse

import httpx

from ..config import Settings, settings as global_settings
from .models import VectorHit, VectorRecord

SQL_PARAMETER_CHUNK = 400

# ``RAG_VECTOR_STORE=auto`` probes Qdrant on every call. A probe to a server that
# is not running blocks for the whole connect timeout (seconds), which used to be
# paid by /api/ai/status, every retrieval and every indexing run. Results are
# cached instead, and a negative result is remembered for longer because a
# missing Qdrant rarely appears mid-session.
VECTOR_STORE_PROBE_TTL_SECONDS = 60.0
VECTOR_STORE_PROBE_DOWN_TTL_SECONDS = 300.0
VECTOR_STORE_PROBE_MAX_TIMEOUT = 0.75

_PROBE_CACHE: dict[tuple[str, str], tuple[float, bool]] = {}
_PROBE_LOCK = threading.Lock()


class VectorStoreUnavailable(RuntimeError):
    """Raised when the configured vector store cannot be used."""


class VectorStore(Protocol):
    name: str
    dimensions: int
    available: bool
    detail: str

    def upsert(self, records: list[VectorRecord]) -> None:
        ...

    def delete(self, ids: list[str]) -> None:
        ...

    def search(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[VectorHit]:
        ...

    def count(self) -> int:
        ...

    def close(self) -> None:
        ...


def pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *[float(value) for value in vector])


def unpack_vector(blob: bytes) -> list[float]:
    """Unpack a little-endian float32 blob into a list."""
    values = array("f")
    values.frombytes(bytes(blob))
    return values.tolist()


try:  # Optional acceleration for the exact SQLite scan.
    import numpy as _np
except ImportError:  # pragma: no cover - numpy ships with the install
    _np = None


def _dot(left: list[float], right) -> float:
    """Dot product of a query vector with a stored vector."""
    if len(left) != len(right) or not left:
        return 0.0
    if _np is not None:
        return float(_np.dot(left, right))
    return sum(map(mul, left, right))


def _chunked(values: list, size: int = SQL_PARAMETER_CHUNK):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def build_sql_filters(filters: dict) -> tuple[str, list]:
    """Translate retrieval filters into SQL conditions on ``rag_documents``."""
    conditions: list[str] = []
    params: list = []

    country_codes = [str(code).upper() for code in filters.get("country_codes") or []]
    if country_codes:
        placeholders = ",".join("?" for _ in country_codes)
        conditions.append(f"country_code IN ({placeholders})")
        params.extend(country_codes)

    categories = [str(category) for category in filters.get("categories") or []]
    if categories:
        placeholders = ",".join("?" for _ in categories)
        conditions.append(f"category IN ({placeholders})")
        params.extend(categories)

    min_importance = filters.get("min_importance")
    if min_importance:
        conditions.append("importance >= ?")
        params.append(int(min_importance))

    date_from = filters.get("date_from_ts")
    if date_from is not None:
        conditions.append("(event_ts IS NOT NULL AND event_ts >= ?)")
        params.append(float(date_from))

    date_to = filters.get("date_to_ts")
    if date_to is not None:
        conditions.append("(event_ts IS NOT NULL AND event_ts <= ?)")
        params.append(float(date_to))

    return " AND ".join(conditions), params


class SqliteVectorStore:
    """Exact vector search inside the application SQLite database.

    The parsed embedding matrix is cached in memory and reused between searches.
    The cache is keyed on a cheap fingerprint of the index (row count, newest
    ``indexed_at`` and total embedding bytes), so any write to the index
    invalidates it automatically without extra bookkeeping.
    """

    name = "sqlite"
    available = True

    def __init__(self, conn_factory, dimensions: int = 768, detail: str | None = None):
        self._conn_factory = conn_factory
        self._conn: sqlite3.Connection | None = None
        self.dimensions = int(dimensions)
        self.detail = detail or "SQLite search index (rag_documents table)"
        self._cache_key: tuple | None = None
        self._cache_ids: list[str] = []
        self._cache_vectors: list[array] = []
        self._cache_rows: dict[str, dict] = {}
        self._cache_matrix = None
        self._cache_position: dict[str, int] = {}

    # -- connection / cache helpers -----------------------------------------

    def _connection(self) -> sqlite3.Connection:
        """Reuse one connection instead of opening a new one per call."""
        if self._conn is not None:
            try:
                self._conn.execute("SELECT 1")
                return self._conn
            except sqlite3.Error:
                # Closed by another thread/task or invalidated by SQLite: reopen.
                self._release()
        self._conn = self._conn_factory()
        return self._conn

    def _release(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass
            self._conn = None

    def _invalidate(self) -> None:
        self._cache_key = None
        self._cache_ids = []
        self._cache_vectors = []
        self._cache_rows = {}
        self._cache_matrix = None
        self._cache_position = {}

    def _signature(self, conn: sqlite3.Connection) -> tuple:
        """Cheap fingerprint of the index state; changes on every write."""
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(indexed_at), ''), "
            "COALESCE(SUM(LENGTH(embedding)), 0) FROM rag_documents"
        ).fetchone()
        return (row[0], row[1], row[2])

    def _matrix(
        self, conn: sqlite3.Connection
    ) -> tuple[list[str], list[array], dict[str, dict]]:
        """Return (ids, vectors, filter columns), decoding embeddings only once."""
        signature = self._signature(conn)
        if self._cache_key == signature:
            return self._cache_ids, self._cache_vectors, self._cache_rows

        ids: list[str] = []
        vectors: list[array] = []
        rows: dict[str, dict] = {}
        for record in conn.execute(
            "SELECT id, embedding, embedding_dim, country_code, category, "
            "importance, event_ts FROM rag_documents "
            "WHERE embedding IS NOT NULL"
        ):
            document_id = record["id"]
            ids.append(document_id)
            decoded = array("f")
            decoded.frombytes(bytes(record["embedding"]))
            vectors.append(decoded)
            rows[document_id] = {
                "embedding_dim": record["embedding_dim"],
                "country_code": record["country_code"],
                "category": record["category"],
                "importance": record["importance"],
                "event_ts": record["event_ts"],
            }

        matrix = None
        if _np is not None and vectors:
            matrix = _np.asarray(vectors, dtype=_np.float32)

        self._cache_key = signature
        self._cache_ids = ids
        self._cache_vectors = vectors
        self._cache_rows = rows
        self._cache_matrix = matrix
        self._cache_position = {document_id: index for index, document_id in enumerate(ids)}
        return ids, vectors, rows

    # -- VectorStore interface ---------------------------------------------

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return

        conn = self._conn_factory()
        try:
            for record in records:
                conn.execute(
                    """
                    UPDATE rag_documents
                    SET embedding = ?, embedding_dim = ?
                    WHERE id = ?
                    """,
                    (pack_vector(record.vector), len(record.vector), record.id),
                )
            conn.commit()
        finally:
            conn.close()
        self._invalidate()

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return

        conn = self._conn_factory()
        try:
            for chunk in _chunked(list(ids)):
                placeholders = ",".join("?" for _ in chunk)
                conn.execute(
                    "UPDATE rag_documents SET embedding = NULL "
                    f"WHERE id IN ({placeholders})",
                    chunk,
                )
            conn.commit()
        finally:
            conn.close()
        self._invalidate()

    def search(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[VectorHit]:
        if not vector:
            return []

        filters = filters or {}
        wanted = max(1, int(limit))
        where, params = build_sql_filters(filters)

        # The decoded embedding matrix is cached, so a search is one matrix
        # multiply plus a sort. Filtered searches ask SQLite for the candidate
        # ids only (cheap, indexed columns) and score just those rows.
        conn = self._connection()
        ids, vectors, rows = self._matrix(conn)
        if not ids:
            return []

        if where:
            candidate_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM rag_documents "
                    "WHERE embedding IS NOT NULL AND " + where,
                    params,
                )
            ]
        else:
            candidate_ids = ids

        if self._cache_matrix is not None:
            query = _np.asarray(vector, dtype=_np.float32)
            scores = self._cache_matrix @ query  # one vectorised pass
            pairs = [
                (document_id, float(scores[self._cache_position[document_id]]))
                for document_id in candidate_ids
                if document_id in self._cache_position
            ]
        else:
            pairs = [
                (
                    document_id,
                    _dot(vector, vectors[self._cache_position[document_id]]),
                )
                for document_id in candidate_ids
                if document_id in self._cache_position
            ]

        hits: list[VectorHit] = []
        for document_id, score in pairs:
            stored_dim = rows[document_id].get("embedding_dim")
            if stored_dim and int(stored_dim) != len(vector):
                # Different embedding dimensions - skip instead of comparing
                # incompatible vectors.
                continue

            if score <= 0:
                continue
            hits.append(VectorHit(id=document_id, score=float(score)))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:wanted]

    def count(self) -> int:
        conn = self._conn_factory()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM rag_documents WHERE embedding IS NOT NULL"
            ).fetchone()
            return int(row["total"] if row else 0)
        finally:
            conn.close()

    def close(self) -> None:
        self._release()


def _point_id(document_id: str) -> int:
    """Qdrant point ids must be integers or UUIDs.

    Event/article ids (``event:123``) are mapped deterministically to a
    positive 63-bit integer so Qdrant never receives an invalid string id.
    """
    import hashlib

    digest = hashlib.sha256(str(document_id).encode("utf-8")).hexdigest()
    return int(digest[:15], 16) % (2**63 - 1) + 1


class QdrantVectorStore:
    """Qdrant backend (remote server or embedded local mode)."""

    name = "qdrant"

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        collection: str = "global_event_intelligence",
        dimensions: int = 768,
        local_path: str | None = None,
        timeout: float = 3.0,
    ):
        self.url = url.rstrip("/")
        self.api_key = api_key or None
        self.collection = collection
        self.dimensions = int(dimensions)
        self.local_path = local_path or None
        self.timeout = float(timeout)
        self.available = False
        self.detail = "Qdrant (not initialised)"
        self._client = None
        self._models = None

    # -- internals ---------------------------------------------------
    def _connect(self):
        if self._client is not None:
            return self._client

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qdrant_models
        except ImportError as exc:
            raise VectorStoreUnavailable(
                "qdrant-client is not installed; install it or set RAG_VECTOR_STORE=sqlite"
            ) from exc

        try:
            if self.local_path:
                client = QdrantClient(path=self.local_path)
                mode = f"embedded local mode at {self.local_path}"
            else:
                client = QdrantClient(
                    url=self.url,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
                client.get_collections()
                mode = f"server at {self.url}"
        except Exception as exc:
            raise VectorStoreUnavailable(f"Qdrant is not reachable: {exc}") from exc

        self._models = qdrant_models
        self._client = client

        try:
            self._ensure_collection()
        except Exception as exc:
            raise VectorStoreUnavailable(
                f"Qdrant collection '{self.collection}' could not be prepared: {exc}"
            ) from exc

        self.available = True
        self.detail = f"Qdrant {mode} (collection '{self.collection}')"
        return client

    def _ensure_collection(self) -> None:
        client = self._client
        exists = False
        try:
            exists = bool(client.collection_exists(self.collection))
        except AttributeError:
            exists = any(
                getattr(item, "name", None) == self.collection
                for item in client.get_collections().collections
            )

        if exists:
            return

        client.create_collection(
            collection_name=self.collection,
            vectors_config=self._models.VectorParams(
                size=self.dimensions,
                distance=self._models.Distance.COSINE,
            ),
        )

    def _build_filter(self, filters: dict | None):
        filters = filters or {}
        conditions = []

        country_codes = [str(code).upper() for code in filters.get("country_codes") or []]
        if country_codes:
            conditions.append(
                self._models.FieldCondition(
                    key="country_code",
                    match=self._models.MatchAny(any=country_codes),
                )
            )

        categories = [str(category) for category in filters.get("categories") or []]
        if categories:
            conditions.append(
                self._models.FieldCondition(
                    key="category",
                    match=self._models.MatchAny(any=categories),
                )
            )

        min_importance = filters.get("min_importance")
        if min_importance:
            conditions.append(
                self._models.FieldCondition(
                    key="importance",
                    range=self._models.Range(gte=int(min_importance)),
                )
            )

        date_from = filters.get("date_from_ts")
        date_to = filters.get("date_to_ts")
        if date_from is not None or date_to is not None:
            conditions.append(
                self._models.FieldCondition(
                    key="event_ts",
                    range=self._models.Range(gte=date_from, lte=date_to),
                )
            )

        if not conditions:
            return None

        return self._models.Filter(must=conditions)

    # -- VectorStore API ---------------------------------------------
    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return

        client = self._connect()
        points = [
            self._models.PointStruct(
                id=_point_id(record.id),
                vector=list(record.vector),
                payload={**record.payload, "doc_id": record.id},
            )
            for record in records
        ]
        client.upsert(collection_name=self.collection, points=points, wait=True)

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return

        client = self._connect()
        point_ids = [_point_id(document_id) for document_id in ids]
        try:
            selector = self._models.PointIdsList(points=point_ids)
            client.delete(collection_name=self.collection, points_selector=selector)
        except AttributeError:
            client.delete(collection_name=self.collection, points_selector=point_ids)

    def search(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[VectorHit]:
        if not vector:
            return []

        client = self._connect()
        query_filter = self._build_filter(filters)
        limit = max(1, int(limit))

        try:
            response = client.query_points(
                collection_name=self.collection,
                query=list(vector),
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
            points = response.points
        except AttributeError:
            points = client.search(
                collection_name=self.collection,
                query_vector=list(vector),
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )

        hits: list[VectorHit] = []
        for point in points:
            payload = getattr(point, "payload", None) or {}
            document_id = payload.get("doc_id") or str(getattr(point, "id", ""))
            hits.append(VectorHit(id=str(document_id), score=float(point.score or 0.0)))

        return hits

    def count(self) -> int:
        try:
            client = self._connect()
            result = client.count(collection_name=self.collection, exact=True)
            return int(getattr(result, "count", 0) or 0)
        except VectorStoreUnavailable:
            return 0

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._client.close()
        except Exception:
            pass
        self._client = None
        self.available = False


_SQLITE_STORE_CACHE: dict[tuple, "SqliteVectorStore"] = {}
_SQLITE_STORE_LOCK = threading.Lock()


def get_sqlite_vector_store(
    conn_factory,
    dimensions: int = 768,
    detail: str | None = None,
) -> "SqliteVectorStore":
    """Return the process-wide SQLite vector store for this database.

    The store owns the decoded embedding matrix cache, so reusing the instance
    is what makes repeat searches cheap. It is keyed by database path, so tests
    that point ``DB_PATH`` at a temporary file get their own instance.
    """
    from ..database import db as db_module

    key = (str(getattr(db_module, "DB_PATH", "")), int(dimensions))
    with _SQLITE_STORE_LOCK:
        store = _SQLITE_STORE_CACHE.get(key)
        if store is None:
            store = SqliteVectorStore(conn_factory, dimensions, detail=detail)
            _SQLITE_STORE_CACHE[key] = store
        elif detail:
            store.detail = detail
        return store


def get_vector_store(config: Settings | None = None) -> VectorStore:
    """Return the configured vector store.

    Raises :class:`VectorStoreUnavailable` when Qdrant was explicitly requested
    (``RAG_VECTOR_STORE=qdrant``) but cannot be reached. In ``auto`` mode the
    SQLite search index is used instead so retrieval keeps working.
    """
    config = config or global_settings
    mode = (config.rag_vector_store or "auto").strip().lower()

    from ..database.db import get_connection

    if mode == "sqlite":
        return get_sqlite_vector_store(
            get_connection, config.rag_embedding_dimensions
        )

    if mode == "qdrant":
        store = QdrantVectorStore(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection=config.qdrant_collection,
            dimensions=config.rag_embedding_dimensions,
            local_path=config.qdrant_local_path,
            timeout=config.qdrant_timeout_seconds,
        )
        store._connect()
        return store

    if mode != "auto":
        raise VectorStoreUnavailable(
            f"Unsupported RAG_VECTOR_STORE '{mode}' (expected auto, sqlite or qdrant)"
        )

    qdrant_configured = bool(config.qdrant_local_path) or qdrant_is_reachable(
        config.qdrant_url,
        timeout=min(config.qdrant_timeout_seconds, VECTOR_STORE_PROBE_MAX_TIMEOUT),
    )

    if qdrant_configured:
        store = QdrantVectorStore(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection=config.qdrant_collection,
            dimensions=config.rag_embedding_dimensions,
            local_path=config.qdrant_local_path,
            timeout=config.qdrant_timeout_seconds,
        )
        try:
            store._connect()
            return store
        except VectorStoreUnavailable as exc:
            return get_sqlite_vector_store(
                get_connection,
                config.rag_embedding_dimensions,
                detail=f"SQLite search index (Qdrant unavailable: {exc})",
            )

    return get_sqlite_vector_store(
        get_connection,
        config.rag_embedding_dimensions,
        detail="SQLite search index (Qdrant not configured)",
    )



def tcp_reachable(url: str, timeout: float = 0.2) -> bool:
    """Fast "is anything listening on this URL's port" check.

    Going through HTTP when the port is closed burns the whole connect timeout,
    and Windows tries both address families, so the cost is paid twice. A plain
    TCP probe settles the common case (an optional Qdrant that is not running)
    in a fraction of that time.
    """
    parsed = urlparse(url if "://" in url else f"http://{url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = parsed.hostname or "localhost"

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    if not infos:
        return False

    def _try(address) -> bool:
        family, socktype, proto, _canon, sockaddr = address
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            return True
        except OSError:
            return False
        finally:
            try:
                sock.close()
            except OSError:
                pass

    # Probe the resolved addresses concurrently so this costs one timeout
    # rather than one timeout per address.
    with ThreadPoolExecutor(max_workers=min(len(infos), 4)) as pool:
        return any(pool.map(_try, infos))


def _probe_qdrant(url: str, timeout: float) -> bool:
    """True only when the endpoint answers the Qdrant collections call."""
    if not tcp_reachable(url, timeout=min(timeout, 0.2)):
        return False
    try:
        response = httpx.get(f"{url.rstrip('/')}/collections", timeout=timeout)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def qdrant_is_reachable(url: str, timeout: float = 1.0, use_cache: bool = True) -> bool:
    """Cheap availability probe used by ``RAG_VECTOR_STORE=auto``.

    Connecting to a Qdrant server that is not running blocks until the connect
    timeout expires (seconds), and this probe runs on every status call, every
    retrieval and every indexing run. Results are cached instead, and a negative
    result is remembered for longer because a missing Qdrant rarely appears
    mid-session.
    """
    key = (url.rstrip("/"), round(float(timeout), 2))
    now = time.monotonic()

    if use_cache:
        with _PROBE_LOCK:
            cached = _PROBE_CACHE.get(key)
            if cached is not None:
                ttl = (
                    VECTOR_STORE_PROBE_TTL_SECONDS
                    if cached[1]
                    else VECTOR_STORE_PROBE_DOWN_TTL_SECONDS
                )
                if (now - cached[0]) < ttl:
                    return cached[1]

    reachable = _probe_qdrant(url, timeout)

    if use_cache:
        with _PROBE_LOCK:
            _PROBE_CACHE[key] = (now, reachable)

    return reachable


def reset_vector_store_probe_cache() -> None:
    """Forget cached Qdrant probes (used by tests and after config changes)."""
    with _PROBE_LOCK:
        _PROBE_CACHE.clear()

