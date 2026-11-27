"""Optional Ollama integration.

The ``ollama`` client package is an **optional** dependency: the platform must
import and run without it (deterministic classification is the default path).
Previously this module imported ``ollama`` at module scope, which made the whole
ingestion service fail to import on any machine without the package.
"""

import asyncio
import json
import logging
import re

from ..config import settings
from .prompts import EVENT_ANALYSIS_PROMPT
from .schemas import EventAnalysis

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by the presence/absence of the package
    import ollama as _ollama
except ImportError:  # pragma: no cover
    _ollama = None


OLLAMA_AVAILABLE = _ollama is not None
MODEL_NAME = settings.ollama_model


def clean_json_response(response: str) -> str:
    """
    Clean Ollama's response so it can be parsed as JSON.
    """

    response = response.strip()

    # Remove Markdown JSON fences
    response = re.sub(
        r"^```json\s*",
        "",
        response,
        flags=re.IGNORECASE,
    )

    response = re.sub(
        r"^```\s*",
        "",
        response,
    )

    response = re.sub(
        r"\s*```$",
        "",
        response,
    )

    return response.strip()


async def analyze_with_ollama(
    title: str,
    description: str = "",
    source: str = "",
    url: str = "",
) -> dict:
    """
    Analyze a news article using Ollama.

    Returns a dictionary containing the AI-generated
    event analysis.
    """

    prompt = EVENT_ANALYSIS_PROMPT.format(
        title=title,
        description=description,
        source=source,
        url=url,
    )

    if _ollama is None:
        raise RuntimeError(
            "The optional `ollama` package is not installed; install it with "
            "`pip install ollama` to enable AI analysis."
        )

    # The ollama Python client is synchronous, so run it through asyncio's
    # thread executor to avoid blocking FastAPI.

    def run_ollama():
        return _ollama.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            options={
                "temperature": 0.1,
            },
        )

    response = await asyncio.to_thread(
        run_ollama
    )

    content = response["message"]["content"]

    cleaned = clean_json_response(
        content
    )

    try:

        data = json.loads(cleaned)

    except json.JSONDecodeError as exc:

        raise ValueError(
            f"Ollama returned invalid JSON: {content}"
        ) from exc

    # Validate against our Pydantic schema
    result = EventAnalysis.model_validate(
        data
    )

    return result.model_dump()