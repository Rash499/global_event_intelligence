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
retention_task: asyncio.Task | None = None

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


@app.on_event("startup")
async def startup():
    global retention_task
    init_db()
    purge_expired_events()
    retention_task = asyncio.create_task(_purge_expired_events_periodically())


@app.on_event("shutdown")
async def shutdown():
    if retention_task:
        retention_task.cancel()
        try:
            await retention_task
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