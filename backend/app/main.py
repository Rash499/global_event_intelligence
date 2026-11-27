"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api.routes import router
from .config import settings
from .database.db import init_db, purge_expired_events
from .security.ratelimit import get_limiter
from .logging_config import configure_logging
from .weather.routes import router as weather_router

logger = logging.getLogger(__name__)

RAG_STARTUP_INDEX_MAX_ROUNDS = 20

app_state: dict = {
    "started_at": None,
    "retention_task": None,
    "rag_index_task": None,
    "scheduler_task": None,
    "migrations": {},
    "ready": False,
}


class ErrorResponseMiddleware:
    """Return a JSON 500 for unhandled errors *without* losing CORS headers.

    Starlette renders unhandled exceptions in ``ServerErrorMiddleware``, which
    sits outside ``CORSMiddleware``, so the browser reports a CORS failure
    instead of a server error. Wrapping the exception here keeps the response
    inside the CORS layer. Tracebacks stay in the logs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if response_started:
                raise
            logger.exception(
                "Unhandled error while handling %s %s",
                scope.get("method", "?"),
                scope.get("path", "?"),
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error. Check the backend logs."},
            )
            await response(scope, receive, send)


async def _purge_expired_events_periodically() -> None:
    while True:
        await asyncio.sleep(max(60, settings.retention_purge_interval_seconds))
        try:
            await asyncio.to_thread(purge_expired_events)
        except Exception:
            logger.exception("Failed to purge expired events")


async def _index_rag_on_startup() -> None:
    """Build the assistant's search index in bounded batches after startup."""
    if not settings.rag_index_on_startup:
        return
    try:
        await asyncio.sleep(max(0.0, settings.rag_index_startup_delay_seconds))
        from .rag.indexer import _INDEX_LOCK, index_pending

        totals = {"indexed": 0, "skipped": 0, "failed": 0}
        for round_number in range(1, RAG_STARTUP_INDEX_MAX_ROUNDS + 1):
            if _INDEX_LOCK.locked():
                break
            async with _INDEX_LOCK:
                result = await index_pending(
                    limit=settings.rag_index_batch_limit, config=settings
                )
            for key in totals:
                totals[key] += getattr(result, key, 0)
            logger.info(
                "[RAG] Startup round %s: %s (indexed=%s skipped=%s failed=%s)",
                round_number, result.status, result.indexed, result.skipped, result.failed,
            )
            if result.status in {"unavailable", "disabled"} or result.indexed == 0:
                break
            await asyncio.sleep(max(0.0, settings.rag_index_startup_pause_seconds))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("[RAG] Startup indexing failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level, settings.log_json)
    logger.info(
        "Starting %s v%s (environment=%s, db=%s)",
        settings.app_name, settings.app_version, settings.environment, settings.db_path,
    )

    migration_summary = await asyncio.to_thread(init_db)
    app_state["migrations"] = migration_summary
    if migration_summary.get("applied"):
        logger.info("Applied database migrations: %s", migration_summary["applied"])
    if migration_summary.get("backup"):
        logger.info("Pre-migration database backup: %s", migration_summary["backup"])

    try:
        from .ingestion.registry import ensure_provider_rows

        ensure_provider_rows()
    except Exception:
        logger.exception("Could not initialise provider registry rows")

    await asyncio.to_thread(purge_expired_events)

    app_state["started_at"] = asyncio.get_event_loop().time()
    app_state["ready"] = True
    app_state["retention_task"] = asyncio.create_task(_purge_expired_events_periodically())
    app_state["rag_index_task"] = asyncio.create_task(_index_rag_on_startup())

    if settings.scheduler_enabled:
        from .scheduler.runner import scheduler_loop

        app_state["scheduler_task"] = asyncio.create_task(scheduler_loop())
        logger.info("Background provider scheduler enabled")

    try:
        yield
    finally:
        app_state["ready"] = False
        for key in ("scheduler_task", "retention_task", "rag_index_task"):
            task = app_state.get(key)
            if task:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Global Event Intelligence Platform API. Multi-source collection, "
        "event correlation, explainable assessments and evidence-grounded AI."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Registered first so CORS ends up outermost and decorates error responses.
app.add_middleware(ErrorResponseMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Fixed-window rate limiting on the API surface.

    Write routes get a much smaller budget than reads (see
    ``security/ratelimit.py``). Health checks are never limited so monitoring
    cannot lock itself out.
    """
    path = request.url.path
    if not path.startswith("/api") or path == "/api/health":
        return await call_next(request)

    # Identity is the caller's token subject when present, otherwise the peer
    # address. The token is not logged or stored.
    auth = request.headers.get("authorization", "")
    identity = auth[-24:] if auth else (request.client.host if request.client else "unknown")
    limiter = get_limiter(settings.api_rate_limit_per_minute)
    allowed, remaining, retry_after = limiter.check(identity, path)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Retry shortly."},
            headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"},
        )

    response = await call_next(request)
    response.headers.setdefault("X-RateLimit-Remaining", str(remaining))
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(router)
app.include_router(weather_router)


@app.get("/", tags=["meta"])
def root():
    return {
        "message": "Global Event Intelligence API",
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs",
        "health": "/api/health",
    }
