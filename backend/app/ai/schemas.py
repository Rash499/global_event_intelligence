from pydantic import BaseModel, Field
from typing import List


class EventAnalysis(BaseModel):
    is_major_event: bool = False

    event_title: str

    category: str

    country: str | None = None

    country_code: str | None = None

    location: str | None = None

    latitude: float | None = None

    longitude: float | None = None

    countries_involved: List[str] = Field(default_factory=list)

    importance: int = Field(default=1, ge=1, le=10)

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    summary: str