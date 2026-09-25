"""EmbeddingGemma input formats, vector checks, and the Ollama request used in milestone 1."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

import httpx

# Neither Ollama's embeddinggemma template nor the sentence-transformers call
# adds a prompt, so the retrieval prefixes are applied here and nowhere else.
DOCUMENT_FORMAT = "title: {title} | text: {text}"
QUERY_FORMAT = "task: search result | query: {question}"
FORMAT_VERSION = hashlib.sha256(f"{DOCUMENT_FORMAT}\n{QUERY_FORMAT}".encode()).hexdigest()[:12]
NORM_TOLERANCE = 1e-3


class EmbeddingError(RuntimeError):
    pass


def format_document(title: str, text: str) -> str:
    return DOCUMENT_FORMAT.format(title=title.strip() or "none", text=text.strip())


def format_query(question: str) -> str:
    return QUERY_FORMAT.format(question=question.strip())


def validate_vectors(vectors: Sequence[Sequence[float]], expected: int, dimensions: int) -> None:
    if len(vectors) != expected:
        raise EmbeddingError(f"expected {expected} vectors, got {len(vectors)}")
    for i, vector in enumerate(vectors):
        if len(vector) != dimensions:
            raise EmbeddingError(f"vector {i} has {len(vector)} values, expected {dimensions}")
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingError(f"vector {i} has a non-finite value")
        if abs(norm(vector) - 1.0) > NORM_TOLERANCE:
            raise EmbeddingError(f"vector {i} is not unit length")


def embed(ollama: str, model: str, inputs: Sequence[str], dimensions: int) -> list[list[float]]:
    """Embed already-formatted inputs. truncate=false makes over-length input an error."""
    if not inputs:
        return []
    response = httpx.post(
        f"{ollama.rstrip('/')}/api/embed",
        json={"model": model, "input": list(inputs), "truncate": False},
        timeout=120,
    )
    response.raise_for_status()
    vectors = response.json().get("embeddings") or []
    validate_vectors(vectors, len(inputs), dimensions)
    return vectors


def norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vectors have different lengths")
    denominator = norm(a) * norm(b)
    if denominator == 0:
        raise ValueError("zero-length vector")
    return sum(x * y for x, y in zip(a, b)) / denominator
