from fastapi import APIRouter

from ..ingestion.service import ingest


router = APIRouter(prefix="/api")


@router.post("/ingestion/run")
async def run_ingestion():
    return await ingest()
