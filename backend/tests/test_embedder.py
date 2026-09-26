import math

import numpy as np
import pytest

from app.doctor import load_lock
from app.embedder import InputTooLong, SentenceTransformerEmbedder, embedder_from_lock
from app.embeddings import EmbeddingError, format_document, format_query

REVISION = "57c266a740f537b4dc058e1b0cda161fd15afa75"


class WordTokenizer:
    def __call__(self, text, add_special_tokens=True):
        ids = list(range(len(text.split())))
        return {"input_ids": [2, *ids, 1] if add_special_tokens else ids}


class FakeModel:
    def __init__(self, max_seq_length=8, default_prompt_name=None):
        self.max_seq_length = max_seq_length
        self.default_prompt_name = default_prompt_name
        self.tokenizer = WordTokenizer()
        self.calls = []

    def encode(self, inputs, **kwargs):
        self.calls.append((inputs, kwargs))
        return np.full((len(inputs), 4), 0.5)


def make(model=None):
    return SentenceTransformerEmbedder("fake/model", REVISION, 4, model=model or FakeModel())


def test_counts_exclude_bos_and_eos():
    embedder = make()
    assert embedder.tokenizer.count("one two three") == 3
    assert embedder.tokenizer.count_with_special("one two three") == 5
    assert embedder.tokenizer.count("   ") == 0
    assert embedder.tokenizer.name == "embeddinggemma-hf-57c266a740f5"


def test_over_limit_input_is_refused_before_encoding():
    model = FakeModel(max_seq_length=8)
    embedder = make(model)
    embedder.embed(["one two three four five six"])
    with pytest.raises(InputTooLong, match="exceed 8 tokens"):
        embedder.embed(["short", "one two three four five six seven"])
    assert len(model.calls) == 1


def test_no_builtin_prompt_is_applied():
    model = FakeModel()
    make(model).embed(["task: search result | query: x"])
    assert model.calls[0][1]["prompt"] is None


def test_default_prompt_is_rejected():
    with pytest.raises(EmbeddingError, match="default prompt"):
        make(FakeModel(default_prompt_name="query"))


def test_non_unit_vectors_are_rejected():
    model = FakeModel()
    model.encode = lambda inputs, **kwargs: np.ones((len(inputs), 4))
    with pytest.raises(EmbeddingError, match="unit length"):
        make(model).embed(["x"])


def test_identity_names_runtime_revision_and_tokenizer():
    identity = make().identity
    assert identity == {
        "runtime": "sentence-transformers",
        "model": "fake/model",
        "revision": REVISION,
        "dimensions": 4,
        "max_seq_length": 8,
        "tokenizer": "embeddinggemma-hf-57c266a740f5",
    }


@pytest.mark.live
def test_real_embeddinggemma_matches_the_lock_and_ranks_the_matching_text():
    lock = load_lock()
    embedder = embedder_from_lock(lock)
    assert embedder.identity["tokenizer"] == lock["embedding"]["tokenizer"]
    assert embedder.max_tokens == lock["embedding"]["max_seq_length"]
    docs = embedder.embed(
        [
            format_document("Baggage", "Bags over 23 kg are tagged heavy."),
            format_document("Security", "Airside doors must stay closed."),
        ]
    )
    query = embedder.embed([format_query("How heavy can a bag be before it is tagged?")])[0]
    scores = [sum(a * b for a, b in zip(query, doc)) for doc in docs]
    assert scores[0] > scores[1]
    assert all(math.isfinite(score) for score in scores)
