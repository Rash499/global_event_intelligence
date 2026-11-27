from fastapi import APIRouter

from .models import WeatherBatchRequest
from .service import get_global_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/health")
def weather_health():
    return {
        "status": "ok",
        "service": "global-weather",
        "source": "Open-Meteo",
        # Open-Meteo's free API is licensed for non-commercial use only
        # (10,000 calls/day); commercial deployments need a paid
        # subscription with Open-Meteo. Data itself is CC BY 4.0.
        "licence_note": "Free Open-Meteo API: non-commercial use only; data CC BY 4.0 (attribution required)",
    }


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
