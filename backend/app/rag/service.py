"""RAG service: end-to-end orchestration for the Global Intelligence Assistant.

Pipeline for one question:

1. deterministic query understanding (:func:`app.rag.query.parse_query`);
2. scope check - out-of-scope questions are refused without touching the LLM;
3. deterministic metrics - SQL aggregates over ``events`` for the same filters;
4. hybrid retrieval (:func:`app.rag.retriever.retrieve`);
5. grounded generation through Ollama with a strict evidence-only prompt;
6. response validation - citations must map to retrieved records and every
   source URL must come from the platform database, never from the model.

Every infrastructure failure (Ollama down, Qdrant down, empty index) is mapped
to a structured :class:`AiAnswer` status instead of an exception, so the API
always answers and the rest of the platform keeps working.
"""

import asyncio
import logging
import re
import time

from ..config import Settings, settings as global_settings
from ..database.db import get_connection
from . import llm as llm_client
from . import prompts
from .embeddings import build_embedding_provider
from .indexer import index_pending, index_stats, indexing_in_progress
from .models import (
    AiAnswer,
    AiQueryRequest,
    AiStatus,
    AnswerMetrics,
    CategoryCount,
    CountryCount,
    EvidenceRecord,
    QueryPlan,
    SourceCitation,
    SuggestionList,
    QuestionSuggestion,
    TimelinePoint,
)
from .query import parse_query
from .retriever import retrieve
from .timestamps import to_epoch, to_iso

logger = logging.getLogger(__name__)

CITATION_RE = re.compile(r"\[(\d{1,3})\]")
SOURCES_LINE_RE = re.compile(r"^\s*Sources used:.*$", re.MULTILINE | re.IGNORECASE)
MAJOR_IMPORTANCE = 7

# Strong references for background tasks so they are not garbage collected.
_background_tasks: set[asyncio.Task] = set()

# Short-lived cache for /api/ai/status. The UI polls it, and each uncached call
# probes the model server and the vector store, which is slow and pointless at
# that frequency.
_STATUS_CACHE: tuple[float, AiStatus] | None = None


def _fail(
    status: str,
    message: str,
    plan: QueryPlan | None = None,
    evidence: list[EvidenceRecord] | None = None,
    metrics: AnswerMetrics | None = None,
    retrieval=None,
    warnings: list[str] | None = None,
    started: float | None = None,
    config: Settings | None = None,
) -> AiAnswer:
    """Build a non-``ok`` answer with evidence attached when we have it."""
    config = config or global_settings
    evidence = evidence or []
    return AiAnswer(
        status=status,  # type: ignore[arg-type]
        answer=None,
        message=message,
        sources=_collect_sources(evidence),
        evidence=evidence,
        retrieved_count=len(evidence),
        metrics=metrics,
        plan=plan,
        retrieval=retrieval,
        validation_warnings=warnings or [],
        grounded=False,
        elapsed_ms=int((time.monotonic() - started) * 1000) if started else 0,
    )


def _collect_sources(evidence: list[EvidenceRecord]) -> list[SourceCitation]:
    """All DB-verified sources of the evidence records, de-duplicated by URL."""
    sources: list[SourceCitation] = []
    seen: set[str] = set()

    for record in evidence:
        for source in record.sources:
            key = source.url or f"{source.source}:{source.title}:{source.article_id}"
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)

    return sources


# ---------------------------------------------------------------------------
# Deterministic metrics (SQL, never the LLM)
# ---------------------------------------------------------------------------

def _metric_conditions(plan: QueryPlan) -> tuple[list[str], list]:
    filters = plan.filters
    conditions: list[str] = []
    params: list = []

    if filters.country_codes:
        placeholders = ",".join("?" for _ in filters.country_codes)
        conditions.append(f"country_code IN ({placeholders})")
        params.extend(filters.country_codes)

    if filters.categories:
        placeholders = ",".join("?" for _ in filters.categories)
        conditions.append(f"category IN ({placeholders})")
        params.extend(filters.categories)

    if filters.min_importance:
        conditions.append("importance >= ?")
        params.append(int(filters.min_importance))

    return conditions, params


def compute_metrics(plan: QueryPlan, config: Settings | None = None) -> AnswerMetrics:
    """SQL aggregates for the same filters used during retrieval."""
    conditions, params = _metric_conditions(plan)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, category, country, country_code, importance, "
            f"event_time, created_at FROM events{where}",
            params,
        ).fetchall()
    finally:
        conn.close()

    date_from = to_epoch(plan.filters.date_from) if plan.filters.date_from else None
    date_to = to_epoch(plan.filters.date_to) if plan.filters.date_to else None

    matching: list[dict] = []
    for row in rows:
        event = dict(row)
        epoch = to_epoch(event.get("event_time")) or to_epoch(event.get("created_at"))
        if date_from is not None and (epoch is None or epoch < date_from):
            continue
        if date_to is not None and (epoch is None or epoch > date_to):
            continue
        event["_epoch"] = epoch
        matching.append(event)

    countries: dict[str, CountryCount] = {}
    categories: dict[str, CategoryCount] = {}
    timeline: dict[str, TimelinePoint] = {}
    major = 0

    for event in matching:
        importance = int(event.get("importance") or 0)
        is_major = importance >= MAJOR_IMPORTANCE
        if is_major:
            major += 1

        country_key = event.get("country") or event.get("country_code") or "unknown"
        entry = countries.setdefault(
            str(country_key),
            CountryCount(
                country=event.get("country"),
                country_code=event.get("country_code"),
            ),
        )
        entry.count += 1
        if is_major:
            entry.major_count += 1

        category_key = str(event.get("category") or "other")
        cat_entry = categories.setdefault(category_key, CategoryCount(category=category_key))
        cat_entry.count += 1
        if is_major:
            cat_entry.major_count += 1

        iso = to_iso(event.get("event_time")) or to_iso(event.get("created_at"))
        day = (iso or "")[:10] or None
        if day:
            point = timeline.setdefault(day, TimelinePoint(date=day))
            point.count += 1
            if is_major:
                point.major_count += 1

    times = [
        to_iso(event.get("event_time")) or to_iso(event.get("created_at"))
        for event in matching
    ]
    times = [value for value in times if value]

    return AnswerMetrics(
        matching_events=len(matching),
        major_events=major,
        countries=sorted(countries.values(), key=lambda item: item.count, reverse=True)[:10],
        categories=sorted(categories.values(), key=lambda item: item.count, reverse=True)[:10],
        timeline=sorted(timeline.values(), key=lambda item: item.date or "", reverse=True)[:30],
        date_from=plan.filters.date_from,
        date_to=plan.filters.date_to,
        earliest_event_time=min(times) if times else None,
    )
# ---------------------------------------------------------------------------
# Answer validation (citations and sources must map to retrieved records)
# ---------------------------------------------------------------------------

def _extract_citations(text: str) -> set[int]:
    return {int(match) for match in CITATION_RE.findall(text or "")}


def _strip_sources_line(text: str) -> str:
    return SOURCES_LINE_RE.sub("", text or "").strip()


def validate_answer(
    raw: str,
    evidence: list[EvidenceRecord],
) -> tuple[str, list[SourceCitation], list[str], bool]:
    """Clean the model output and map citations onto retrieved evidence.

    Returns ``(answer, sources, warnings, grounded)``. Citations that do not
    point at a retrieved record are removed, and sources are taken exclusively
    from the evidence records (which were re-hydrated from SQLite), so the
    response can never contain an invented URL.
    """
    warnings: list[str] = []
    valid_numbers = {record.record_number for record in evidence}
    cited = _extract_citations(raw)

    unknown = cited - valid_numbers
    if unknown:
        warnings.append(prompts.UNKNOWN_CITATION_WARNING)

    answer = raw.strip()
    if unknown:
        # Remove the bogus markers so the UI never shows a dangling reference.
        def _replace(match: re.Match) -> str:
            return "" if int(match.group(1)) in unknown else match.group(0)

        answer = CITATION_RE.sub(_replace, answer)
        answer = re.sub(r"[ \t]{2,}", " ", answer)
        answer = re.sub(r"\s+([,.;:])", r"\1", answer)

    known_cited = cited & valid_numbers
    cited_records = [
        record for record in evidence if record.record_number in known_cited
    ]

    sources: list[SourceCitation] = []
    if cited_records:
        sources = _collect_sources(cited_records)
    else:
        # No usable citations: still expose the retrieved evidence as context
        # (all of it came from the database), but flag the answer as ungrounded.
        sources = _collect_sources(evidence)

    grounded = bool(known_cited) and not _is_refusal(answer)

    # Rebuild the "Sources used" line from validated citations only.
    answer = _strip_sources_line(answer)
    if known_cited:
        ordered = ", ".join(f"[{number}]" for number in sorted(known_cited))
        answer = f"{answer}\n\nSources used: {ordered}".strip()

    return answer, sources, warnings, grounded


def _is_refusal(answer: str) -> bool:
    return prompts.REFUSAL_SENTENCE.strip().lower() in (answer or "").strip().lower()


def _has_refusal(answer: str) -> bool:
    return prompts.REFUSAL_SENTENCE.strip().lower() in (answer or "").lower()
# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def _auto_index_if_needed(config: Settings) -> None:
    """Best-effort incremental indexing so brand-new events are searchable.

    Runs in the background by default: embedding a batch of documents took
    tens of seconds on a local model server, and doing that inline delayed the
    user's answer by that much. The current query simply uses the index as it
    is; the top-up applies to the next one.
    """
    if not config.rag_auto_index_on_query:
        return
    if indexing_in_progress():
        return  # a startup/ingestion run is already doing this work

    try:
        stats = index_stats(config=config)
        if stats["pending_documents"] <= 0 and stats["indexed_documents"] > 0:
            return
    except Exception:  # noqa: BLE001 - indexing problems must not block queries
        logger.warning("[RAG] Auto-index stats failed", exc_info=True)
        return

    if config.rag_auto_index_background:
        task = asyncio.create_task(
            index_pending(limit=config.rag_auto_index_limit, config=config)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return

    try:
        await index_pending(limit=config.rag_auto_index_limit, config=config)
    except Exception:  # noqa: BLE001 - indexing problems must not block queries
        logger.warning("[RAG] Auto-index before query failed", exc_info=True)


async def answer(request: AiQueryRequest, config: Settings | None = None) -> AiAnswer:
    """Answer one assistant question end to end. Never raises."""
    config = config or global_settings
    started = time.monotonic()
    warnings: list[str] = []

    if not config.rag_enabled:
        return _fail("disabled", prompts.DISABLED_MESSAGE, started=started, config=config)

    # 1. Deterministic query understanding.
    try:
        plan = parse_query(request.question, request.conversation, request.filters, config)
    except Exception as exc:  # noqa: BLE001 - malformed input must not 500
        logger.exception("[RAG] Query parsing failed")
        return _fail(
            "error",
            f"The question could not be parsed: {exc}",
            started=started,
            config=config,
        )

    if plan.prompt_injection_detected:
        warnings.append(prompts.PROMPT_INJECTION_WARNING)

    # Optional incremental indexing so brand-new events are searchable.
    await _auto_index_if_needed(config)

    # 2. Scope check before spending any model time.
    if plan.out_of_scope:
        return AiAnswer(
            status="out_of_scope",
            answer=None,
            message=prompts.out_of_scope_message(plan.out_of_scope_reason),
            plan=plan,
            validation_warnings=warnings,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    # 3. Deterministic metrics for the prompt and the UI.
    try:
        metrics = compute_metrics(plan, config)
    except Exception:  # noqa: BLE001
        logger.exception("[RAG] Metrics computation failed")
        metrics = None

    # 4. Hybrid retrieval.
    try:
        evidence, diagnostics = await retrieve(plan, config)
    except Exception as exc:  # noqa: BLE001 - retrieval must degrade, not raise
        logger.exception("[RAG] Retrieval failed")
        return _fail(
            "retrieval_unavailable",
            prompts.RETRIEVAL_UNAVAILABLE_MESSAGE,
            plan=plan,
            metrics=metrics,
            warnings=warnings,
            started=started,
            config=config,
        )

    if not evidence:
        return AiAnswer(
            status="insufficient_data",
            answer=None,
            message=prompts.NO_RECORDS_MESSAGE,
            metrics=metrics,
            plan=plan,
            retrieval=diagnostics,
            validation_warnings=warnings,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    # 5. LLM availability.
    llm_ok, llm_detail = await llm_client.is_available(config)
    if not llm_ok:
        answer_text = prompts.LLM_UNAVAILABLE_MESSAGE
        return AiAnswer(
            status="llm_unavailable",
            answer=answer_text,
            message=llm_detail or prompts.LLM_UNAVAILABLE_MESSAGE,
            sources=_collect_sources(evidence),
            evidence=evidence,
            retrieved_count=len(evidence),
            metrics=metrics,
            plan=plan,
            retrieval=diagnostics,
            validation_warnings=warnings,
            llm_model=config.chat_model,
            llm_available=False,
            grounded=False,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    # 6. Grounded generation.
    context = prompts.build_context(
        evidence,
        config.rag_max_context_documents,
        config.rag_max_context_characters,
    )
    user_prompt = prompts.USER_PROMPT_TEMPLATE.format(
        context=context,
        metrics=prompts.format_metrics(metrics),
        question_type=plan.question_type,
        filters=prompts.format_filters(plan),
        conversation_block=prompts.format_conversation(request.conversation),
        question=plan.question,
    )

    try:
        raw = await llm_client.chat(prompts.SYSTEM_PROMPT, user_prompt, config)
    except llm_client.LLMError as exc:
        logger.warning("[RAG] LLM call failed: %s", exc)
        return AiAnswer(
            status="llm_unavailable",
            answer=prompts.LLM_UNAVAILABLE_MESSAGE,
            message=str(exc),
            sources=_collect_sources(evidence),
            evidence=evidence,
            retrieved_count=len(evidence),
            metrics=metrics,
            plan=plan,
            retrieval=diagnostics,
            validation_warnings=warnings,
            llm_model=config.chat_model,
            llm_available=False,
            grounded=False,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    # 7. Validation: citations and sources must map to retrieved records.
    answer_text, sources, validation_warnings, grounded = validate_answer(raw, evidence)
    warnings.extend(validation_warnings)

    status = "ok"
    message = None
    if _has_refusal(answer_text):
        status = "insufficient_data"
        message = prompts.INSUFFICIENT_ANSWER_WARNING

    return AiAnswer(
        status=status,  # type: ignore[arg-type]
        answer=answer_text,
        message=message,
        sources=sources,
        evidence=evidence,
        retrieved_count=len(evidence),
        metrics=metrics,
        plan=plan,
        retrieval=diagnostics,
        validation_warnings=warnings,
        llm_model=config.chat_model,
        llm_available=True,
        grounded=grounded,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
# ---------------------------------------------------------------------------
# Status and suggestions (used by the UI)
# ---------------------------------------------------------------------------

async def status(config: Settings | None = None, force: bool = False) -> AiStatus:
    """Report assistant availability without ever raising.

    Cached briefly: the assistant UI polls this endpoint, and an uncached call
    probes the model server and the vector store, which costs seconds.
    """
    config = config or global_settings
    global _STATUS_CACHE

    ttl = max(0.0, float(config.rag_status_cache_ttl_seconds))
    if not force and _STATUS_CACHE is not None and ttl > 0:
        cached_at, cached = _STATUS_CACHE
        if (time.monotonic() - cached_at) < ttl:
            return cached

    notes: list[str] = []

    llm_ok, llm_detail = await llm_client.is_available(config)
    if llm_detail:
        notes.append(llm_detail)

    embedding_provider = None
    embedding_model = None
    embedding_available = False
    try:
        provider = build_embedding_provider(config)
        embedding_provider = provider.name
        embedding_model = provider.model
        probe = getattr(provider, "is_available", None)
        if probe is not None:
            embedding_available = bool(await probe())
        else:
            embedding_available = True
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Embedding provider unavailable: {exc}")

    vector_store_name = None
    vector_store_detail = None
    vector_store_available = False
    try:
        from .vector_store import get_vector_store

        store = get_vector_store(config)
        vector_store_name = store.name
        vector_store_detail = store.detail
        vector_store_available = bool(getattr(store, "available", True))
        store.close()
    except Exception as exc:  # noqa: BLE001
        vector_store_available = False
        vector_store_detail = str(exc)
        notes.append(f"Vector store unavailable: {exc}")

    try:
        stats = index_stats(config=config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RAG] Index stats failed: %s", exc)
        stats = {}

    if stats.get("indexed_documents", 0) == 0:
        notes.append(
            "The search index is empty. Run Collect News or POST /api/ai/index "
            "to index the database."
        )

    result = AiStatus(
        enabled=config.rag_enabled,
        llm_available=llm_ok,
        chat_model=config.chat_model,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_available=embedding_available,
        vector_store=vector_store_name,
        vector_store_available=vector_store_available,
        vector_store_detail=vector_store_detail,
        indexed_documents=int(stats.get("indexed_documents", 0) or 0),
        indexed_events=int(stats.get("indexed_events", 0) or 0),
        pending_documents=int(stats.get("pending_documents", 0) or 0),
        last_indexed_at=stats.get("last_indexed_at"),
        top_k=config.rag_top_k,
        max_context_documents=config.rag_max_context_documents,
        notes=notes,
    )

    if ttl > 0:
        _STATUS_CACHE = (time.monotonic(), result)

    return result


STATIC_SUGGESTIONS = [
    QuestionSuggestion(
        id="latest",
        label="What are the latest major events?",
        question="What are the latest major events?",
    ),
    QuestionSuggestion(
        id="natural-disasters",
        label="Any major natural disasters?",
        question="What major natural disasters happened recently?",
    ),
    QuestionSuggestion(
        id="top-countries",
        label="Which countries have the most events?",
        question="Which countries have the most events right now?",
    ),
    QuestionSuggestion(
        id="importance",
        label="Show high-importance events",
        question="What high importance events are happening right now?",
    ),
    QuestionSuggestion(
        id="sources",
        label="Which events have the most sources?",
        question="Which events have the most sources reporting them?",
    ),
]


def suggestions(config: Settings | None = None) -> SuggestionList:
    """Static starter questions plus a few derived from the database."""
    config = config or global_settings
    derived: list[QuestionSuggestion] = []

    conn = get_connection()
    try:
        top_country = conn.execute(
            "SELECT country, country_code, COUNT(*) AS n FROM events "
            "WHERE country IS NOT NULL AND TRIM(country) != '' "
            "GROUP BY country_code ORDER BY n DESC LIMIT 1"
        ).fetchone()
        if top_country:
            derived.append(
                QuestionSuggestion(
                    id=f"country-{top_country['country_code']}",
                    label=f"What happened in {top_country['country']}?",
                    question=f"What happened in {top_country['country']} recently?",
                    origin="data",
                )
            )

        top_category = conn.execute(
            "SELECT category, COUNT(*) AS n FROM events "
            "GROUP BY category ORDER BY n DESC LIMIT 1"
        ).fetchone()
        if top_category:
            derived.append(
                QuestionSuggestion(
                    id=f"category-{top_category['category']}",
                    label=f"Latest {top_category['category'].replace('_', ' ')} events",
                    question=(
                        f"What are the latest events in the "
                        f"{top_category['category'].replace('_', ' ')} category?"
                    ),
                    origin="data",
                )
            )

        latest = conn.execute(
            "SELECT MAX(COALESCE(event_time, created_at)) AS t FROM events"
        ).fetchone()
        latest_time = latest["t"] if latest else None
    finally:
        conn.close()

    return SuggestionList(
        suggestions=STATIC_SUGGESTIONS + derived,
        generated_from="platform database",
        latest_event_time=latest_time,
        computed_by="platform SQL aggregates",
    )





