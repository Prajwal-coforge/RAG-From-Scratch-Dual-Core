"""EmbeddingGemma through sentence-transformers, pinned to one revision.

Inputs arrive already formatted by app.embeddings, so the model's built-in
query/document prompts are never used. sentence-transformers truncates at
max_seq_length without warning; every input is counted first and refused
if it would not fit.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from app.embeddings import EmbeddingError, validate_vectors

BATCH_SIZE = 16


class InputTooLong(EmbeddingError):
    pass


class HFTokenizer:
    """Counts text tokens with the embedder's own tokenizer, without BOS/EOS."""

    def __init__(self, tokenizer, revision: str):
        self._tokenizer = tokenizer
        self.name = f"embeddinggemma-hf-{revision[:12]}"

    def count(self, text: str) -> int:
        if not text or not text.strip():
            return 0
        return len(self._tokenizer(text, add_special_tokens=False)["input_ids"])

    def count_with_special(self, text: str) -> int:
        return len(self._tokenizer(text, add_special_tokens=True)["input_ids"])


class SentenceTransformerEmbedder:
    runtime = "sentence-transformers"

    def __init__(self, model_id: str, revision: str, dimensions: int, *, model=None):
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_id, revision=revision)
        self.model_id = model_id
        self.revision = revision
        self.dimensions = dimensions
        self._model = model
        if self._model.default_prompt_name is not None:
            raise EmbeddingError("the model applies a default prompt; inputs would get a second prefix")
        self.max_tokens = int(self._model.max_seq_length)
        self.tokenizer = HFTokenizer(self._model.tokenizer, revision)

    @property
    def identity(self) -> dict:
        return {
            "runtime": self.runtime,
            "model": self.model_id,
            "revision": self.revision,
            "dimensions": self.dimensions,
            "max_seq_length": self.max_tokens,
            "tokenizer": self.tokenizer.name,
        }

    def check_lengths(self, inputs: Sequence[str]) -> list[int]:
        counts = [self.tokenizer.count_with_special(text) for text in inputs]
        over = [(i, n) for i, n in enumerate(counts) if n > self.max_tokens]
        if over:
            index, count = over[0]
            raise InputTooLong(
                f"{len(over)} input(s) exceed {self.max_tokens} tokens (first: #{index}, {count} tokens); "
                "refusing instead of letting sentence-transformers truncate"
            )
        return counts

    def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        if not inputs:
            return []
        self.check_lengths(inputs)
        array = self._model.encode(
            list(inputs), batch_size=BATCH_SIZE, prompt=None, convert_to_numpy=True, show_progress_bar=False
        )
        vectors = [[float(value) for value in row] for row in array]
        validate_vectors(vectors, len(inputs), self.dimensions)
        return vectors


class OllamaEmbedder:
    """The milestone 1 embedder. Kept so the recorded proof can be reproduced."""

    runtime = "ollama"

    def __init__(self, ollama: str, model: str, blob_digest: str, dimensions: int):
        self.ollama = ollama.rstrip("/")
        self.model_id = model
        self.revision = blob_digest
        self.dimensions = dimensions

    @property
    def identity(self) -> dict:
        return {"runtime": self.runtime, "model": self.model_id, "revision": self.revision, "dimensions": self.dimensions}

    def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        from app.embeddings import embed

        return embed(self.ollama, self.model_id, inputs, self.dimensions)


@lru_cache(maxsize=2)
def load_embedder(model_id: str, revision: str, dimensions: int) -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder(model_id, revision, dimensions)


def embedder_from_lock(lock: dict) -> SentenceTransformerEmbedder:
    spec = lock["embedding"]
    return load_embedder(spec["model"], spec["revision"], spec["dimensions"])
