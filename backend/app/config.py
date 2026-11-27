"""Centralised, validated application settings.

Everything the application can be configured with lives here and is read from
the environment (or ``backend/.env``).  The previous implementation advertised a
``DATABASE_URL`` setting while ``database/db.py`` ignored it and always opened
``backend/data/events.db``; the two are now a single source of truth:
``DATABASE_URL`` is authoritative and ``DB_PATH`` is derived from it.

Never commit real secrets.  ``.env.example`` documents every variable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = "Global Event Intelligence API"
    app_version: str = "0.2.0"
    environment: str = "development"  # development | test | production
    log_level: str = "INFO"
    # Pretty, single-line console logs by default; set false for JSON lines.
    log_json: bool = False

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    # ``sqlite:///./data/events.db`` (relative to backend/) or an absolute
    # path such as ``sqlite:////var/lib/gei/events.db``.
    database_url: str = "sqlite:///./data/events.db"
    db_busy_timeout_ms: int = 30000
    # WAL lets one writer and many readers work concurrently. Disable only on
    # filesystems without shared-memory support.
    db_wal_enabled: bool = True
    # Take a timestamped copy of the database before destructive migrations.
    db_backup_before_migration: bool = True

    # ------------------------------------------------------------------
    # HTTP / API
    # ------------------------------------------------------------------
    # Comma separated list of frontend origins allowed to call the API.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Demo seed route + fabricated sample data. Never enable in production.
    demo_data_enabled: bool = False
    api_rate_limit_per_minute: int = 240
    external_request_timeout_seconds: float = 20.0

    # ------------------------------------------------------------------
    # AI (Ollama)
    # ------------------------------------------------------------------
    ollama_enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    # Two-stage hybrid classification: deterministic rules first, then (opt-in)
    # the model when the deterministic pass is not confident enough.
    ai_classification_enabled: bool = False
    ai_classification_min_confidence: float = 0.72
    ai_classification_max_per_cycle: int = 10

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    gdelt_max_records: int = 50
    gdelt_languages: str = "english,spanish,french,german,arabic"
    gdelt_time_window_hours: int = 24
    # GDELT asks clients to send at most one request every 5 seconds and
    # answers bursts with HTTP 429. The provider paces every request (across
    # query profiles and collection retries) to this interval and honours
    # Retry-After / exponential backoff on 429 before giving up on a profile.
    gdelt_request_interval_seconds: float = 5.0
    gdelt_throttle_max_retries: int = 2
    rss_max_entries_per_feed: int = 30
    google_news_max_per_query: int = 20
    google_news_language: str = "en-US"
    google_news_country: str = "US"
    ingestion_max_articles_per_cycle: int = 60
    ingestion_timeout_seconds: float = 25.0
    provider_max_retries: int = 3
    provider_retry_backoff_seconds: float = 2.0
    # A provider that fails this many consecutive times is circuit-broken for
    # ``provider_circuit_cooldown_seconds``.
    provider_circuit_failure_threshold: int = 4
    provider_circuit_cooldown_seconds: int = 900

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------
    scheduler_enabled: bool = False
    scheduler_rss_interval_seconds: int = 900
    scheduler_gdelt_interval_seconds: int = 1800
    scheduler_google_news_interval_seconds: int = 1800
    scheduler_usgs_interval_seconds: int = 600
    scheduler_eonet_interval_seconds: int = 3600
    scheduler_gdacs_interval_seconds: int = 1800
    scheduler_reliefweb_interval_seconds: int = 3600
    scheduler_who_interval_seconds: int = 3600
    scheduler_firms_interval_seconds: int = 3600
    scheduler_cap_interval_seconds: int = 600
    scheduler_tick_seconds: int = 30

    # ------------------------------------------------------------------
    # Optional intelligence providers
    # ------------------------------------------------------------------
    # USGS needs no credentials.
    usgs_enabled: bool = True
    usgs_feed_url: str = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    usgs_min_magnitude: float = 2.5
    usgs_max_features: int = 200

    # NASA EONET v3: public API, no key or registration required.
    # https://eonet.gsfc.nasa.gov/docs/v3
    eonet_enabled: bool = True
    eonet_base_url: str = "https://eonet.gsfc.nasa.gov/api/v3"
    eonet_days: int = 30
    eonet_max_events: int = 200

    # GDACS (UN/EC Global Disaster Alert and Coordination System): public
    # REST API, no authentication required.
    # https://www.gdacs.org/gdacsapi/swagger/index.html
    gdacs_enabled: bool = True
    gdacs_api_url: str = "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/latest"
    gdacs_max_events: int = 100

    # ReliefWeb API v2 (v1 is decommissioned). Since 1 Nov 2025 the
    # ``appname`` must be pre-approved by ReliefWeb via their request form:
    # https://apidoc.reliefweb.int/ - an unapproved appname gets HTTP 403.
    reliefweb_enabled: bool = False
    reliefweb_appname: str = ""
    reliefweb_base_url: str = "https://api.reliefweb.int/v2"
    reliefweb_max_records: int = 50

    # WHO Disease Outbreak News (public RSS, no key).
    who_enabled: bool = True
    who_feed_url: str = "https://www.who.int/feeds/entity/csr/don/en/rss.xml"
    who_max_entries: int = 30

    # NASA FIRMS requires a free MAP_KEY.
    firms_enabled: bool = False
    firms_map_key: str = ""
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
    firms_source: str = "VIIRS_SNPP_NRT"
    firms_day_range: int = 1
    firms_max_detections: int = 500
    # bbox = min_lon,min_lat,max_lon,max_lat (defaults to a global-ish view).
    firms_bbox: str = "-180,-85,180,85"

    # Common Alerting Protocol feeds (comma separated ). No credentials.
    cap_feed_urls: str = ""

    # ACLED requires registration/OAuth; the connector validates configuration
    # and reports ``not_configured`` until credentials are supplied.
    acled_enabled: bool = False
    acled_access_token: str = ""
    acled_base_url: str = "https://api.acleddata.com/acled/read"

    # ------------------------------------------------------------------
    # Intelligence assessment
    # ------------------------------------------------------------------
    # Half-life (hours) used to decay the weight of older reports in the
    # confidence score.
    confidence_recency_half_life_hours: float = 36.0
    # A report older than this no longer contributes independent confirmation.
    confidence_max_report_age_hours: float = 168.0
    # Domains that aggregate/syndicate other publishers rather than reporting.
    syndication_domains: str = (
        "news.google.com,yahoo.com,msn.com,flipboard.com,smartnews.com,"
        "newsnow.co.uk,newsbreak.com,ground.news,apple.news"
    )

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------
    # Events and their articles are retained for this many days. The retention
    # purge runs hourly. This value is authoritative and documented in README.
    historical_retention_days: int = 365
    retention_purge_interval_seconds: int = 3600
    retention_article_days: int = 365

    # ------------------------------------------------------------------
    # Geolocation
    # ------------------------------------------------------------------
    # Geolocation is intentionally local-gazetteer based only (see
    # intelligence/geolocation.py): no external geocoding service is called.
    # The previous GEOCODING_* (Nominatim) settings were removed because no
    # code ever called that endpoint, and the public Nominatim instance's
    # usage policy prohibits bulk/heavy automated geocoding. The
    # ``geocoding_source``/``geocoding_confidence`` event columns remain and
    # record the local extraction source.

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    # Hosts that external fetches may never reach (in addition to the private
    # range checks performed by the SSRF guard).
    ssrf_allow_private_hosts: bool = False
    ssrf_max_redirects: int = 3
    ssrf_max_response_bytes: int = 1_500_000
    ssrf_timeout_seconds: float = 8.0

    # ------------------------------------------------------------------
    # Phase 3 - grounded RAG assistant
    # ------------------------------------------------------------------
    rag_enabled: bool = True
    ollama_chat_model: str | None = None
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_request_timeout_seconds: float = 120.0
    ollama_availability_timeout_seconds: float = 2.0
    ollama_num_ctx: int = 4096
    ollama_max_tokens: int = 512
    ollama_temperature: float = 0.1

    # Default is the offline hashing embedder so a fresh clone works with no
    # Ollama install and no cost. Set to "ollama" only with a local Ollama;
    # if Ollama is configured but unreachable, embedding falls back to
    # hashing automatically (see rag/embeddings.py).
    rag_embedding_provider: str = "hashing"
    rag_embedding_dimensions: int = 768
    rag_embedding_batch_size: int = 16

    rag_vector_store: str = "auto"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "global_event_intelligence"
    qdrant_local_path: str | None = None
    qdrant_timeout_seconds: float = 3.0

    rag_top_k: int = 8
    rag_max_context_documents: int = 10
    rag_max_context_characters: int = 12000
    rag_candidate_pool: int = 400
    rag_vector_weight: float = 0.6
    rag_lexical_weight: float = 0.4
    rag_min_relevance: float = 0.05

    rag_index_batch_limit: int = 300
    rag_ingestion_index_limit: int = 25
    rag_index_on_startup: bool = True
    rag_index_startup_delay_seconds: float = 8.0
    rag_index_startup_pause_seconds: float = 2.0
    rag_auto_index_on_query: bool = True
    rag_auto_index_limit: int = 64
    rag_auto_index_background: bool = True
    rag_status_cache_ttl_seconds: float = 5.0
    rag_llm_availability_cache_ttl_seconds: float = 15.0

    rag_max_conversation_turns: int = 6
    rag_cache_ttl_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        normalised = (value or "development").strip().lower()
        if normalised not in {"development", "test", "production"}:
            raise ValueError(
                "ENVIRONMENT must be one of development, test, production"
            )
        return normalised

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        parsed = urlparse((value or "").strip())
        if parsed.scheme != "sqlite":
            raise ValueError(
                "Only sqlite:/// DATABASE_URL values are supported by this "
                "deployment. Point DATABASE_URL at a SQLite file."
            )
        if not parsed.path or parsed.path in {"/", "//"}:
            raise ValueError("DATABASE_URL must include a database file path")
        return value.strip()

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            if self.demo_data_enabled:
                # Fail fast instead of silently accepting fabricated records.
                raise ValueError(
                    "DEMO_DATA_ENABLED cannot be enabled when ENVIRONMENT=production"
                )
            if "*" in self.cors_origins:
                raise ValueError(
                    "Wildcard CORS origins are not allowed in production"
                )
        return self

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------
    @property
    def db_path(self) -> Path:
        """Absolute SQLite file path derived from ``DATABASE_URL``.

        Follows the SQLAlchemy convention:

        * ``sqlite:///./data/events.db``  -> relative to ``backend/``
        * ``sqlite:////var/lib/gei.db``   -> absolute path
        """
        rest = self.database_url.split("sqlite:", 1)[-1]
        if rest.startswith("////"):
            candidate = Path("/" + rest.lstrip("/"))
        elif rest.startswith("///"):
            candidate = Path(rest[3:])
        else:  # sqlite:/relative or bare path
            candidate = Path(rest.lstrip("/"))
        if not candidate.is_absolute():
            candidate = (BASE_DIR / candidate).resolve()
        return candidate

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def chat_model(self) -> str:
        return (self.ollama_chat_model or self.ollama_model).strip()

    @property
    def ollama_root(self) -> str:
        return self.ollama_url.rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def syndication_domain_set(self) -> set[str]:
        return {
            domain.strip().lower()
            for domain in self.syndication_domains.split(",")
            if domain.strip()
        }

    @property
    def cap_feed_url_list(self) -> list[str]:
        return [url.strip() for url in self.cap_feed_urls.split(",") if url.strip()]

    @property
    def gdelt_language_list(self) -> list[str]:
        return [lang.strip() for lang in self.gdelt_languages.split(",") if lang.strip()]

    def ensure_data_dir(self) -> Path:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return self.db_path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings", "BASE_DIR"]
