from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database.db import init_db
from .api.routes import router
from .weather.routes import router as weather_router


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


@app.on_event("startup")
def startup():
    init_db()


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