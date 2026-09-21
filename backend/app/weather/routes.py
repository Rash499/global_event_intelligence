from fastapi import APIRouter

from .models import WeatherBatchRequest
from .service import get_global_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/health")
def weather_health():
    return {"status": "ok", "service": "global-weather"}


@router.post("/global")
async def global_weather(payload: WeatherBatchRequest):
    locations = [item.model_dump() for item in payload.locations]
    results = await get_global_weather(locations)
    return {
        "source": "Open-Meteo",
        "forecast_days": 7,
        "locations": results,
        "count": len(results),
    }
