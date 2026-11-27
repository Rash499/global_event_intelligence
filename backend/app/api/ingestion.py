import asyncio
import logging

from fastapi import APIRouter, HTTPException

from ..ingestion.service import ingest

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_ingestion_lock = asyncio.Lock()


@router.post("/ingestion/run")
async def run_ingestion(providers: str | None = None):
    """Run one ingestion cycle at a time.

    The ingestion pipeline talks to several remote feeds and optionally Ollama.
    Preventing overlapping runs avoids concurrent SQLite writers when the UI
    refreshes or the user clicks Collect News while an automatic run is active.
    """
    if _ingestion_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="News collection is already running. Please wait for the current run to finish.",
        )

    requested = (
        [key.strip() for key in providers.split(",") if key.strip()]
        if providers
        else None
    )

    async with _ingestion_lock:
        try:
            return await ingest(providers=requested)
        except Exception as exc:
            logger.exception("Ingestion failed")
            raise HTTPException(
                status_code=503,
                detail=f"News collection failed: {type(exc).__name__}. Check the backend logs for details.",
            ) from exc


@router.get("/ingestion/status")
def ingestion_status():
    """Whether a collection run is in progress, and the last run summary."""
    from ..ingestion.registry import collection_history, enabled_provider_keys

    history = collection_history(limit=5)
    return {
        "running": _ingestion_lock.locked(),
        "enabled_providers": enabled_provider_keys(),
        "recent_runs": history,
    }
