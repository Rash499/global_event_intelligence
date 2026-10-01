"""Phase 3 endpoints for the Global Intelligence Assistant.

All endpoints degrade gracefully: they return structured JSON with an
``AiAnswer``/``AiStatus`` payload instead of failing when Ollama, Qdrant or the
search index are unavailable, so the frontend can explain the situation and
Phases 1/2 keep working.
"""

from fastapi import APIRouter, Depends

from ..config import settings
from ..rag.indexer import index_pending
from ..rag.models import AiQueryRequest, IndexRequest, IndexResult
from ..rag import service as rag_service
from .auth import get_optional_user

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/query")
async def ask(payload: AiQueryRequest, user=Depends(get_optional_user)):
    """Answer one grounded question with evidence and DB-verified sources."""
    return await rag_service.answer(payload, settings)


@router.get("/status")
async def assistant_status(
    refresh: bool = False, user=Depends(get_optional_user)
):
    """Availability of the assistant: Ollama, embeddings, vector store, index.

    The result is cached briefly because the UI polls this endpoint; pass
    ``?refresh=true`` (used after indexing) to bypass the cache.
    """
    return await rag_service.status(settings, force=refresh)


@router.get("/suggestions")
async def assistant_suggestions(user=Depends(get_optional_user)):
    """Starter questions (static + derived from the platform database)."""
    return rag_service.suggestions(settings)


@router.post("/index")
async def run_index(
    payload: IndexRequest | None = None, user=Depends(get_optional_user)
) -> IndexResult:
    """Run (or re-run) incremental indexing of the SQLite database.

    Never raises: embedding/vector-store failures are reported in the
    ``IndexResult`` so ingestion and the rest of the platform are unaffected.
    """
    payload = payload or IndexRequest()
    result = await index_pending(
        limit=payload.limit,
        force=payload.force,
        config=settings,
    )
    # Index counts just changed, so drop the cached status.
    await rag_service.status(settings, force=True)
    return result
