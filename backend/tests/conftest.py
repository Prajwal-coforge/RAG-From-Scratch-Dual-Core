import hashlib

import numpy as np
import pytest

from app.embedder import SentenceTransformerEmbedder


class WordTokenizer:
    """Counts whitespace-separated words; BOS and EOS are added like Gemma's."""

    def __call__(self, text, add_special_tokens=True):
        ids = list(range(len(text.split())))
        return {"input_ids": [2, *ids, 1] if add_special_tokens else ids}


class HashModel:
    """Deterministic unit vectors from a text hash, so equal inputs get equal vectors."""

    def __init__(self, max_seq_length=2048, dimensions=8):
        self.max_seq_length = max_seq_length
        self.default_prompt_name = None
        self.tokenizer = WordTokenizer()
        self.dimensions = dimensions

    def encode(self, inputs, **kwargs):
        rows = []
        for text in inputs:
            digest = hashlib.sha256(text.encode()).digest()
            row = np.frombuffer(digest[: self.dimensions], dtype=np.uint8).astype(float) + 1.0
            rows.append(row / np.linalg.norm(row))
        return np.array(rows)


@pytest.fixture
def make_embedder():
    def build(max_seq_length=2048, revision="0" * 40, model_id="fake/embeddinggemma"):
        model = HashModel(max_seq_length=max_seq_length)
        return SentenceTransformerEmbedder(model_id, revision, model.dimensions, model=model)

    return build
