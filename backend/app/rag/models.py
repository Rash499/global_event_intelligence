"""Pydantic models for the Phase 3 RAG layer.

These models are the contract between the indexer, the retriever, the LLM
service, the API layer and the React UI. Anything the assistant returns to the
frontend is validated against :class:`AiAnswer` so raw model output never
reaches the browser unchecked.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DocumentType = Literal["event", "article"]

QuestionType = Literal[
    "latest",
    "country",
    "category",
    "historical",
    "comparison",
    "sources",
    "event_details",
    "importance",
    "aggregate",
    "semantic",
]

AnswerStatus = Literal[
    "ok",
    "insufficient_data",
    "out_of_scope",
    "llm_unavailable",
    "retrieval_unavailable",
    "disabled",
    "error",
]

RetrievalMode = Literal["hybrid", "lexical", "vector", "none"]

RelevanceLabel = Literal["strong", "moderate", "limited", "none"]

MAX_QUESTION_LENGTH = 500
MAX_CONVERSATION_TURNS = 8


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationTurn(BaseModel):
    """A single turn of the (frontend-held) conversation context."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class QueryOverrides(BaseModel):
    """Optional explicit filters supplied by the client (advanced use)."""

    country_code: str | None = Field(default=None, max_length=3)
    category: str | None = Field(default=None, max_length=40)
    min_importance: int | None = Field(default=None, ge=1, le=10)
    days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("country_code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class AiQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_LENGTH)
    conversation: list[ConversationTurn] = Field(
        default_factory=list, max_length=MAX_CONVERSATION_TURNS
    )
    top_k: int | None = Field(default=None, ge=1, le=20)
    filters: QueryOverrides | None = None

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        cleaned = " ".join(value.replace("\x00", " ").split())
        if len(cleaned) < 3:
            raise ValueError("Question is too short")
        return cleaned


class IndexRequest(BaseModel):
    force: bool = False
    limit: int | None = Field(default=None, ge=1, le=5000)


class QueryFilters(BaseModel):
    """Structured constraints extracted from the question (and/or client)."""

    country_codes: list[str] = Field(default_factory=list)
    region: str | None = None
    categories: list[str] = Field(default_factory=list)
    min_importance: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    keywords: list[str] = Field(default_factory=list)
    time_range_label: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.country_codes,
                self.categories,
                self.min_importance,
                self.date_from,
                self.date_to,
            ]
        )


class QueryPlan(BaseModel):
    """Result of deterministic query understanding."""

    question: str
    normalized: str
    tokens: list[str] = Field(default_factory=list)
    question_type: QuestionType = "semantic"
    filters: QueryFilters = Field(default_factory=QueryFilters)
    comparison_countries: list[str] = Field(default_factory=list)
    wants_sources: bool = False
    follow_up: bool = False
    out_of_scope: bool = False
    out_of_scope_reason: str | None = None
    prompt_injection_detected: bool = False



class IndexDocument(BaseModel):
    """A searchable document derived from the platform database."""

    id: str
    document_type: DocumentType
    event_id: int | None = None
    article_id: int | None = None
    title: str = ""
    text: str
    document_hash: str
    country: str | None = None
    country_code: str | None = None
    category: str | None = None
    importance: int | None = None
    confidence: float | None = None
    source: str | None = None
    url: str | None = None
    published_at: str | None = None
    event_time: str | None = None


class VectorRecord(BaseModel):
    id: str
    vector: list[float]
    payload: dict = Field(default_factory=dict)


class VectorHit(BaseModel):
    id: str
    score: float


class SourceCitation(BaseModel):
    """A traceable source. URLs always come from the platform database."""

    index: int
    document_type: DocumentType
    event_id: int | None = None
    article_id: int | None = None
    title: str | None = None
    source: str | None = None
    url: str | None = None
    published_at: str | None = None
    verified_in_database: bool = False
    record_number: int | None = None


class EvidenceRecord(BaseModel):
    """One retrieved platform record used as evidence for an answer."""

    record_number: int
    document_type: DocumentType = "event"
    event_id: int | None = None
    title: str
    summary: str = ""
    category: str | None = None
    country: str | None = None
    country_code: str | None = None
    importance: int | None = None
    confidence: float | None = None
    corroboration_level: str | None = None
    article_count: int | None = None
    source_count: int | None = None
    source_domains: list[str] = Field(default_factory=list)
    event_time: str | None = None
    published_at: str | None = None
    relevance: float = 0.0
    matched_on: str = "event"
    sources: list[SourceCitation] = Field(default_factory=list)


class RetrievalDiagnostics(BaseModel):
    mode: RetrievalMode = "none"
    vector_store: str = "none"
    vector_store_detail: str | None = None
    vector_search_available: bool = True
    documents_indexed: int = 0
    candidates_scanned: int = 0
    top_score: float = 0.0
    relevance: RelevanceLabel = "none"
    filters_applied: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class CountryCount(BaseModel):
    country: str | None = None
    country_code: str | None = None
    count: int = 0
    major_count: int = 0


class CategoryCount(BaseModel):
    category: str | None = None
    count: int = 0
    major_count: int = 0


class TimelinePoint(BaseModel):
    date: str | None = None
    count: int = 0
    major_count: int = 0


class AnswerMetrics(BaseModel):
    """Deterministic, application-computed metrics (never LLM guesses)."""

    matching_events: int = 0
    major_events: int = 0
    countries: list[CountryCount] = Field(default_factory=list)
    categories: list[CategoryCount] = Field(default_factory=list)
    timeline: list[TimelinePoint] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None
    earliest_event_time: str | None = None


class AiAnswer(BaseModel):
    status: AnswerStatus = "ok"
    answer: str | None = None
    message: str | None = None
    sources: list[SourceCitation] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    retrieved_count: int = 0
    metrics: AnswerMetrics | None = None
    plan: QueryPlan | None = None
    retrieval: RetrievalDiagnostics | None = None
    validation_warnings: list[str] = Field(default_factory=list)
    llm_model: str | None = None
    llm_available: bool = False
    grounded: bool = False
    elapsed_ms: int = 0
    created_at: str = Field(default_factory=_utc_now)


class AiStatus(BaseModel):
    enabled: bool = True
    llm_available: bool = False
    chat_model: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_available: bool = False
    vector_store: str | None = None
    vector_store_available: bool = False
    vector_store_detail: str | None = None
    indexed_documents: int = 0
    indexed_events: int = 0
    pending_documents: int = 0
    last_indexed_at: str | None = None
    top_k: int = 8
    max_context_documents: int = 10
    notes: list[str] = Field(default_factory=list)


class IndexResult(BaseModel):
    status: Literal["ok", "disabled", "unavailable", "partial"] = "ok"
    message: str | None = None
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    pruned: int = 0
    embedding_model: str | None = None
    vector_store: str | None = None
    errors: list[str] = Field(default_factory=list)
    elapsed_ms: int = 0


class QuestionSuggestion(BaseModel):
    id: str
    label: str
    question: str
    origin: Literal["static", "data"] = "static"


class SuggestionList(BaseModel):
    suggestions: list[QuestionSuggestion] = Field(default_factory=list)
    generated_from: str = "platform database"

    latest_event_time: str | None = None
    sources_cited: int = 0
    computed_by: str = "platform SQL aggregates"
