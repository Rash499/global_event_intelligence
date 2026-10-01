"""SQLite schema for the RAG search index.

The ``rag_documents`` table is the RAG *ledger*:

* it stores the searchable text, structured metadata and the incremental
  indexing state (``document_hash``, ``embedding_model``, ``indexed_at``);
* it is also the storage for the default SQLite vector backend, which keeps the
  embedding in the ``embedding`` column;
* when the Qdrant backend is used the vectors live in Qdrant and the ledger
  keeps the incremental state plus the metadata needed for hybrid retrieval.

SQLite stays the source of truth for events and articles; this table is a
derived search index and can always be rebuilt from the database.
"""

RAG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rag_documents (
    id TEXT PRIMARY KEY,
    document_type TEXT NOT NULL,
    event_id INTEGER,
    article_id INTEGER,
    title TEXT,
    text TEXT NOT NULL,
    country TEXT,
    country_code TEXT,
    category TEXT,
    importance INTEGER,
    confidence REAL,
    source TEXT,
    url TEXT,
    published_at TEXT,
    event_time TEXT,
    event_ts REAL,
    document_hash TEXT NOT NULL,
    embedding_model TEXT,
    embedding_dim INTEGER,
    embedding BLOB,
    status TEXT NOT NULL DEFAULT 'indexed',
    error TEXT,
    indexed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_event
    ON rag_documents(event_id);

CREATE INDEX IF NOT EXISTS idx_rag_documents_article
    ON rag_documents(article_id);

CREATE INDEX IF NOT EXISTS idx_rag_documents_type
    ON rag_documents(document_type);

CREATE INDEX IF NOT EXISTS idx_rag_documents_country
    ON rag_documents(country_code);

CREATE INDEX IF NOT EXISTS idx_rag_documents_category
    ON rag_documents(category);

CREATE INDEX IF NOT EXISTS idx_rag_documents_importance
    ON rag_documents(importance);

CREATE INDEX IF NOT EXISTS idx_rag_documents_event_ts
    ON rag_documents(event_ts);

CREATE INDEX IF NOT EXISTS idx_rag_documents_status
    ON rag_documents(status);
"""


def ensure_rag_schema(conn) -> None:
    """Create the RAG ledger table when it is missing (idempotent)."""
    conn.executescript(RAG_SCHEMA_SQL)
    conn.commit()
