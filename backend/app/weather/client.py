from __future__ import annotations

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "precipitation_probability",
    "weather_code",
    "wind_speed_10m",
    "wind_gusts_10m",
]

DAILY_VARIABLES = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
]


async def fetch_weather_batch(locations: list[dict]) -> list[dict]:
    if not locations:
        return []

    latitude = ",".join(str(item["latitude"]) for item in locations)
    longitude = ",".join(str(item["longitude"]) for item in locations)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(CURRENT_VARIABLES),
        "daily": ",".join(DAILY_VARIABLES),
        "forecast_days": 7,
        "timezone": "auto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()

    # Open-Meteo returns a list when multiple coordinates are requested.
    if isinstance(data, dict):
        return [data]
    return data
