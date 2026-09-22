from fastapi import APIRouter

from .countries import router as countries_router
from .events import router as events_router
from .health import router as health_router
from .ingestion import router as ingestion_router
from .statistics import router as statistics_router


router = APIRouter()

router.include_router(health_router)
router.include_router(events_router)
router.include_router(countries_router)
router.include_router(statistics_router)
router.include_router(ingestion_router)
