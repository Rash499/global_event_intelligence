from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Global Event Intelligence API"
    database_url: str = "sqlite:///./data/events.db"
    ollama_enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    gdelt_max_records: int = 50
    historical_retention_days: int = 365
    # Only ingest articles published within this many hours of collection.
    news_lookback_hours: int = 24

    # ------------------------------------------------------------------
    # Phase 3 - grounded RAG assistant
    # ------------------------------------------------------------------

    # Master switch. When false the assistant reports that it is disabled but
    # every other platform feature keeps working.
    rag_enabled: bool = True

    # Ollama settings. ``ollama_model`` stays the ingestion chat model for
    # backwards compatibility; the assistant prefers ``ollama_chat_model``.
    ollama_chat_model: str | None = None
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_request_timeout_seconds: float = 120.0
    ollama_availability_timeout_seconds: float = 2.0
    ollama_num_ctx: int = 4096
    # Bound the generated answer. Without a cap a small local model keeps
    # writing until it decides it is done, which is what made the assistant feel
    # like it was hanging (20s+ answers). 512 tokens is a few solid paragraphs.
    ollama_max_tokens: int = 512
    ollama_temperature: float = 0.1

    # Embedding strategy: ``ollama`` (default) or ``hashing`` (deterministic
    # offline lexical embedding used for tests and for environments without
    # an embedding model).
    rag_embedding_provider: str = "ollama"
    rag_embedding_dimensions: int = 768
    rag_embedding_batch_size: int = 16

    # Vector store: ``auto`` | ``sqlite`` | ``qdrant``.
    # ``auto`` uses Qdrant when it is reachable and falls back to the SQLite
    # search index otherwise. ``qdrant`` reports retrieval as unavailable when
    # Qdrant cannot be reached instead of silently falling back.
    rag_vector_store: str = "auto"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "global_event_intelligence"
    qdrant_local_path: str | None = None
    qdrant_timeout_seconds: float = 3.0

    # Retrieval / context sizing
    rag_top_k: int = 8
    rag_max_context_documents: int = 10
    rag_max_context_characters: int = 12000
    rag_candidate_pool: int = 400
    rag_vector_weight: float = 0.6
    rag_lexical_weight: float = 0.4
    rag_min_relevance: float = 0.05

    # Indexing
    rag_index_batch_limit: int = 300
    # Small batch for the background run that follows a news cycle: only the
    # handful of new events needs embedding, and a large batch makes every
    # collection run compete with the rest of the system for the model server.
    rag_ingestion_index_limit: int = 25
    rag_index_on_startup: bool = True
    rag_index_startup_delay_seconds: float = 8.0
    # Pause between startup batches so the backend stays responsive while the
    # index is being built.
    rag_index_startup_pause_seconds: float = 2.0
    rag_auto_index_on_query: bool = True
    rag_auto_index_limit: int = 64
    # Run the pre-query top-up in the background instead of blocking the answer.
    rag_auto_index_background: bool = True
    # /api/ai/status is polled by the UI; cache it briefly so polling cannot
    # hammer the model server with availability probes.
    rag_status_cache_ttl_seconds: float = 5.0
    # Availability of the chat model changes rarely, so it is cached separately
    # (and for longer) than the rest of the status payload.
    rag_llm_availability_cache_ttl_seconds: float = 15.0

    # Conversation / caching
    rag_max_conversation_turns: int = 6
    rag_cache_ttl_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def chat_model(self) -> str:
        """Chat model used for grounded answers (falls back to the ingestion model)."""
        return (self.ollama_chat_model or self.ollama_model).strip()

    @property
    def ollama_root(self) -> str:
        return self.ollama_url.rstrip("/")


settings = Settings()

