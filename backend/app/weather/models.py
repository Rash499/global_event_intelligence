from pydantic import BaseModel, Field


class WeatherLocation(BaseModel):
    country_code: str = Field(min_length=2, max_length=3)
    country: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class WeatherBatchRequest(BaseModel):
    locations: list[WeatherLocation] = Field(min_length=1, max_length=250)
