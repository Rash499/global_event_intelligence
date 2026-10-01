"""Embedding providers for the RAG index.

Two providers are supported and both are configurable through the environment:

``ollama``
    Uses the local Ollama server (``OLLAMA_EMBEDDING_MODEL``, by default
    ``nomic-embed-text``) through ``POST /api/embed``. This is the default
    semantic embedding used by the assistant.

``hashing``
    A deterministic, dependency-free feature-hashing embedder. It produces
    lexical (bag-of-words) vectors instead of semantic ones. It exists so the
    whole RAG pipeline stays runnable and testable when no embedding model is
    installed, and so tests never depend on a running Ollama server.

Both providers return L2-normalised vectors, so cosine similarity is a plain
dot product.
"""

import asyncio
import hashlib
import math
import re
from typing import Iterable, Protocol

import httpx

from ..config import Settings, settings as global_settings
from .vector_store import tcp_reachable

WORD_RE = re.compile(r"[a-z0-9]+")

# Words that carry no retrieval signal. Based on the Phase 1 deduplication stop
# words plus common question words.
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "for", "to", "and", "with",
    "after", "before", "into", "from", "by", "as", "over", "under",
    "is", "are", "was", "were", "be", "been", "do", "does", "did",
    "what", "which", "who", "whom", "when", "where", "why", "how", "that",
    "this", "these", "those", "there", "here", "it", "its", "any", "all",
    "me", "my", "our", "you", "your", "we", "us", "they", "them", "their",
    "about", "tell", "show", "give", "list", "please", "can", "could",
    "would", "should", "during", "between", "than", "then", "also",
}

MIN_TOKEN_LENGTH = 2
HASH_DIMENSION_MIN = 64
HASH_DIMENSION_MAX = 4096


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot produce vectors."""


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    async def embed(self, texts: Iterable[str]) -> list[list[float]]:
        ...


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens with stop words removed."""
    if not text:
        return []

    return [
        token
        for token in WORD_RE.findall(text.lower())
        if len(token) >= MIN_TOKEN_LENGTH and token not in STOPWORDS
    ]


def tokenize_with_bigrams(text: str) -> list[str]:
    """Unigrams plus bigrams, used to give phrase matches extra weight."""
    tokens = tokenize(text)
    bigrams = [f"{left} {right}" for left, right in zip(tokens, tokens[1:])]
    return tokens + bigrams


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return [0.0] * len(vector)
    return [value / norm for value in vector]


def dot_product(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


class HashingEmbeddingProvider:
    """Deterministic offline embedder (signed feature hashing)."""

    name = "hashing"

    def __init__(self, dimensions: int = 768):
        self.dimensions = max(HASH_DIMENSION_MIN, min(HASH_DIMENSION_MAX, int(dimensions)))
        self.model = f"hashing-{self.dimensions}d-v1"

    def _hash_token(self, token: str) -> tuple[int, float]:
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % self.dimensions
        sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
        return index, sign

    def embed_sync(self, texts: Iterable[str]) -> list[list[float]]:
        vectors = []

        for text in texts:
            vector = [0.0] * self.dimensions
            for token in tokenize_with_bigrams(text):
                index, sign = self._hash_token(token)
                vector[index] += sign

            vectors.append(normalize_vector(vector))

        return vectors

    async def embed(self, texts: Iterable[str]) -> list[list[float]]:
        """Async interface shared with :class:`OllamaEmbeddingProvider`.

        Hashing is pure CPU work, so the vectors are computed inline instead of
        being pushed onto a thread pool.
        """
        return self.embed_sync(texts)


class OllamaEmbeddingProvider:
    """Embeddings from a local Ollama server (``POST /api/embed``)."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        dimensions: int = 768,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model.strip() or "nomic-embed-text"
        self.dimensions = int(dimensions)
        self.timeout = float(timeout)

    async def _post(self, client: httpx.AsyncClient, path: str, payload: dict) -> dict:
        try:
            response = await client.post(f"{self.base_url}{path}", json=payload)
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                f"Ollama embedding endpoint {path} is not reachable: {exc}"
            ) from exc

        if response.status_code == 404:
            raise LookupError(path)

        if response.status_code >= 400:
            detail = response.text[:200].replace("\n", " ")
            raise EmbeddingError(
                f"Ollama embedding request failed ({response.status_code}): {detail}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise EmbeddingError("Ollama returned a non-JSON embedding response") from exc

    async def embed(self, texts: Iterable[str]) -> list[list[float]]:
        inputs = [str(text) for text in texts]

        if not inputs:
            return []

        # Fail fast when Ollama is not listening instead of waiting for the HTTP
        # connect timeout (paid once per resolved address). This runs on the
        # assistant query path, so a stopped model server must not stall it.
        if not await asyncio.to_thread(tcp_reachable, self.base_url, 0.2):
            raise EmbeddingError(
                f"Ollama embedding server is not reachable at {self.base_url}"
            )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = await self._post(
                    client,
                    "/api/embed",
                    {"model": self.model, "input": inputs},
                )
                raw_vectors = payload.get("embeddings") or []
            except LookupError:
                # Older Ollama releases only expose /api/embeddings.
                raw_vectors = []
                for text in inputs:
                    legacy = await self._post(
                        client,
                        "/api/embeddings",
                        {"model": self.model, "prompt": text},
                    )
                    raw_vectors.append(legacy.get("embedding") or [])

        if len(raw_vectors) != len(inputs):
            raise EmbeddingError(
                f"Ollama returned {len(raw_vectors)} embeddings for {len(inputs)} inputs"
            )

        vectors: list[list[float]] = []
        for vector in raw_vectors:
            values = [float(value) for value in vector]
            if not values:
                raise EmbeddingError("Ollama returned an empty embedding vector")
            vectors.append(normalize_vector(values))

        return vectors

    async def is_available(self, timeout: float | None = None) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=timeout or min(self.timeout, 5.0)
            ) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False


def build_embedding_provider(config: Settings | None = None) -> EmbeddingProvider:
    """Create the configured embedding provider."""
    config = config or global_settings
    provider = (config.rag_embedding_provider or "ollama").strip().lower()

    if provider in {"hashing", "hash", "offline"}:
        return HashingEmbeddingProvider(config.rag_embedding_dimensions)

    if provider != "ollama":
        raise EmbeddingError(
            f"Unsupported RAG_EMBEDDING_PROVIDER '{provider}' "
            "(expected 'ollama' or 'hashing')"
        )

    return OllamaEmbeddingProvider(
        base_url=config.ollama_root,
        model=config.ollama_embedding_model,
        dimensions=config.rag_embedding_dimensions,
        timeout=config.ollama_request_timeout_seconds,
    )
