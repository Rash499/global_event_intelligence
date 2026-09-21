from __future__ import annotations


WEATHER_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

SEVERE_CODES = {65, 67, 75, 82, 86, 95, 96, 99}
HEAVY_PRECIP_CODES = {63, 65, 67, 80, 81, 82}


def weather_description(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return WEATHER_DESCRIPTIONS.get(int(code), "Unknown")


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def temperature_score(temp: float | None) -> float:
    if temp is None:
        return 0

    # This is intentionally a simple visualization heuristic, not a medical
    # or official heat/cold warning model.
    if temp >= 45:
        return 100
    if temp >= 40:
        return 88
    if temp >= 35:
        return 70
    if temp >= 32:
        return 45
    if temp <= -15:
        return 100
    if temp <= -5:
        return 75
    if temp <= 0:
        return 50
    return 0


def precipitation_score(
    precipitation_mm: float | None,
    probability: float | None,
    weather_code: int | None,
) -> float:
    amount = precipitation_mm or 0
    probability = probability or 0

    amount_score = clamp(amount * 3.0)
    probability_score = clamp(probability * 0.45)
    code_bonus = 25 if weather_code in HEAVY_PRECIP_CODES else 0

    return clamp(max(amount_score, probability_score) + code_bonus)


def wind_score(speed_kmh: float | None, gust_kmh: float | None) -> float:
    speed = speed_kmh or 0
    gust = gust_kmh or 0

    speed_score = clamp((speed - 35) * 2.0)
    gust_score = clamp((gust - 50) * 1.8)
    return max(speed_score, gust_score)


def severe_weather_score(weather_code: int | None) -> float:
    if weather_code in {95, 96, 99}:
        return 100
    if weather_code in {65, 67, 75, 82, 86}:
        return 75
    if weather_code in {63, 80, 81}:
        return 45
    if weather_code in {61, 71, 73, 85}:
        return 25
    return 0


def calculate_daily_score(
    temperature_max: float | None,
    precipitation: float | None,
    precipitation_probability: float | None,
    wind_speed: float | None,
    wind_gust: float | None,
    weather_code: int | None,
) -> tuple[float, dict[str, float]]:
    factors = {
        "temperature": temperature_score(temperature_max),
        "precipitation": precipitation_score(
            precipitation, precipitation_probability, weather_code
        ),
        "wind": wind_score(wind_speed, wind_gust),
        "severe_weather": severe_weather_score(weather_code),
    }

    # Weighting is intentionally transparent and deterministic.
    score = (
        factors["temperature"] * 0.25
        + factors["precipitation"] * 0.30
        + factors["wind"] * 0.20
        + factors["severe_weather"] * 0.25
    )

    return round(clamp(score), 1), factors


def severity_label(score: float) -> str:
    if score >= 81:
        return "Extreme"
    if score >= 61:
        return "High"
    if score >= 41:
        return "Moderate"
    if score >= 21:
        return "Low"
    return "Normal"


def calculate_current_score(current: dict) -> tuple[float, dict[str, float]]:
    return calculate_daily_score(
        current.get("temperature_2m"),
        current.get("precipitation"),
        current.get("precipitation_probability"),
        current.get("wind_speed_10m"),
        current.get("wind_gusts_10m"),
        current.get("weather_code"),
    )
