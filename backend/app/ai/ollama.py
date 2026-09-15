import json
import httpx
from ..config import settings

async def analyze_with_ollama(title: str, description: str):
    if not settings.ollama_enabled:
        return None

    prompt = f"""
Analyze this news item and return ONLY valid JSON.
Fields:
category: one of politics, conflict, natural_disaster, economy, technology, health, environment, international
country: country name or null
importance: integer 1-10
summary: concise factual summary

Title: {title}
Description: {description}
"""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            raw = response.json().get("response", "")
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start:end+1])
    except Exception:
        return None
    return None
