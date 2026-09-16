import json
import re

import ollama

from .prompts import EVENT_ANALYSIS_PROMPT
from .schemas import EventAnalysis


MODEL_NAME = "llama3.2:3b"


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

    # The ollama Python client is synchronous,
    # so run it through asyncio's thread executor
    # to avoid blocking FastAPI.
    import asyncio

    def run_ollama():
        return ollama.chat(
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