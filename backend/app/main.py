import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database.db import init_db, purge_expired_events
from .api.routes import router
from .weather.routes import router as weather_router


logger = logging.getLogger(__name__)
RETENTION_INTERVAL_SECONDS = 60
# Safety bound for the startup indexing loop (each round stops early once a
# round indexes nothing new).
RAG_STARTUP_INDEX_MAX_ROUNDS = 20
retention_task: asyncio.Task | None = None
rag_index_task: asyncio.Task | None = None

app = FastAPI(
    title=settings.app_name,
    version="0.1.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return a JSON 500 instead of letting the error escape the CORS middleware.

    Starlette renders unhandled exceptions outside ``CORSMiddleware``, so the
    browser reports them as CORS failures. Handling them here keeps the CORS
    headers on the response and logs the real traceback server side.
    """
    logger.exception(
        "Unhandled error while handling %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check the backend logs."},
    )


async def _purge_expired_events_periodically():
    while True:
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)
        try:
            purge_expired_events()
        except Exception:
            logger.exception("Failed to purge expired events")


async def _index_rag_on_startup():
    """Build/refresh the Phase 3 search index shortly after startup.

    Runs in bounded batches, pausing between them and yielding to the event loop,
    so the backend stays responsive while the index is built: a full rebuild used
    to embed hundreds of documents back to back and made every request feel slow.
    Failures are logged only - the platform must boot and serve Phases 1/2 even
    when Ollama or Qdrant are offline.
    """
    if not settings.rag_index_on_startup:
        return

    try:
        await asyncio.sleep(max(0.0, settings.rag_index_startup_delay_seconds))
        from .rag.indexer import _INDEX_LOCK, index_pending

        totals = {"indexed": 0, "skipped": 0, "failed": 0}
        status = "ok"
        for round_number in range(1, RAG_STARTUP_INDEX_MAX_ROUNDS + 1):
            if _INDEX_LOCK.locked():
                logger.info(
                    "[RAG] Startup indexing: another run is active, standing down"
                )
                break

            async with _INDEX_LOCK:
                result = await index_pending(
                    limit=settings.rag_index_batch_limit,
                    config=settings,
                )

            status = result.status
            for key in totals:
                totals[key] += getattr(result, key, 0)

            logger.info(
                "[RAG] Startup indexing round %s: %s (indexed=%s skipped=%s failed=%s)",
                round_number,
                result.status,
                result.indexed,
                result.skipped,
                result.failed,
            )

            if result.status in {"unavailable", "disabled"}:
                break
            if result.indexed == 0:
                break  # nothing left that this run can improve on

            # Give the event loop (and any user request) room to breathe.
            await asyncio.sleep(max(0.0, settings.rag_index_startup_pause_seconds))

        logger.info(
            "[RAG] Startup indexing finished: %s (indexed=%s skipped=%s failed=%s)",
            status,
            totals["indexed"],
            totals["skipped"],
            totals["failed"],
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("[RAG] Startup indexing failed")


@app.on_event("startup")
async def startup():
    global retention_task, rag_index_task
    init_db()
    purge_expired_events()
    retention_task = asyncio.create_task(_purge_expired_events_periodically())
    rag_index_task = asyncio.create_task(_index_rag_on_startup())


@app.on_event("shutdown")
async def shutdown():
    for task in (retention_task, rag_index_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# Existing API routes
app.include_router(router)

# Weather API routes
app.include_router(weather_router)


@app.get("/")
def root():
    return {
        "message": "Global Event Intelligence API",
        "docs": "/docs"
    }