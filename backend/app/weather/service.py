from __future__ import annotations

import asyncio

from .client import fetch_weather_batch
from .scoring import (
    calculate_current_score,
    calculate_daily_score,
    severity_label,
    weather_description,
)

BATCH_SIZE = 50


def _value(values: list | None, index: int, default=None):
    if not values or index >= len(values):
        return default
    return values[index]


def _round_or_none(value, digits=1):
    if value is None:
        return None
    return round(float(value), digits)


def normalize_weather(location: dict, raw: dict) -> dict:
    current_raw = raw.get("current", {})
    daily_raw = raw.get("daily", {})

    current_code = current_raw.get("weather_code")
    current = {
        "time": current_raw.get("time"),
        "temperature_2m": _round_or_none(current_raw.get("temperature_2m")),
        "apparent_temperature": _round_or_none(current_raw.get("apparent_temperature")),
        "precipitation": _round_or_none(current_raw.get("precipitation")),
        "precipitation_probability": _round_or_none(
            current_raw.get("precipitation_probability"), 0
        ),
        "weather_code": current_code,
        "weather_description": weather_description(current_code),
        "wind_speed_10m": _round_or_none(current_raw.get("wind_speed_10m")),
        "wind_gusts_10m": _round_or_none(current_raw.get("wind_gusts_10m")),
    }

    current_score, current_factors = calculate_current_score(current)

    dates = daily_raw.get("time", [])
    daily = []
    max_forecast_score = 0
    max_forecast_factors = current_factors

    for index, date in enumerate(dates):
        code = _value(daily_raw.get("weather_code"), index)
        temp_max = _value(daily_raw.get("temperature_2m_max"), index)
        temp_min = _value(daily_raw.get("temperature_2m_min"), index)
        precipitation = _value(daily_raw.get("precipitation_sum"), index, 0)
        probability = _value(
            daily_raw.get("precipitation_probability_max"), index, 0
        )
        wind = _value(daily_raw.get("wind_speed_10m_max"), index, 0)
        gust = _value(daily_raw.get("wind_gusts_10m_max"), index, 0)

        score, factors = calculate_daily_score(
            temp_max,
            precipitation,
            probability,
            wind,
            gust,
            code,
        )

        if score > max_forecast_score:
            max_forecast_score = score
            max_forecast_factors = factors

        daily.append(
            {
                "date": date,
                "weather_code": code,
                "weather_description": weather_description(code),
                "temperature_max": _round_or_none(temp_max),
                "temperature_min": _round_or_none(temp_min),
                "precipitation_sum": _round_or_none(precipitation),
                "precipitation_probability_max": _round_or_none(probability, 0),
                "wind_speed_max": _round_or_none(wind),
                "wind_gusts_max": _round_or_none(gust),
                "score": score,
                "severity": severity_label(score),
            }
        )

    forecast_score = round(max_forecast_score, 1)
    overall_score = round(max(current_score, forecast_score), 1)

    # For the dashboard we expose the factors that explain the highest-risk
    # condition currently or in the forecast.
    if forecast_score >= current_score:
        risk_factors = max_forecast_factors
    else:
        risk_factors = current_factors

    return {
        **location,
        "timezone": raw.get("timezone"),
        "current": current,
        "current_score": current_score,
        "forecast_score": forecast_score,
        "score": overall_score,
        "severity": severity_label(overall_score),
        "risk_factors": risk_factors,
        "daily": daily,
    }


async def get_global_weather(locations: list[dict]) -> list[dict]:
    # Open-Meteo supports multiple coordinates in one request. Batching keeps
    # URLs manageable and prevents one very large request from becoming fragile.
    results: list[dict] = []

    for start in range(0, len(locations), BATCH_SIZE):
        batch = locations[start : start + BATCH_SIZE]
        raw_results = await fetch_weather_batch(batch)

        for location, raw in zip(batch, raw_results):
            results.append(normalize_weather(location, raw))

    return results
