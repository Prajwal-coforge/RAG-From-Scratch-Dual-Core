import math

import pytest

from app.embeddings import EmbeddingError, cosine, format_document, format_query, validate_vectors


def _unit(dimensions: int, hot: int = 0) -> list[float]:
    vector = [0.0] * dimensions
    vector[hot] = 1.0
    return vector


def test_document_and_query_prefixes_are_applied_once():
    assert format_document("Baggage | 4 Allowance", "Bags over 23 kg need a tag.") == (
        "title: Baggage | 4 Allowance | text: Bags over 23 kg need a tag."
    )
    assert format_query("  How heavy can a bag be? ") == "task: search result | query: How heavy can a bag be?"


def test_missing_title_uses_none():
    assert format_document("", "text") == "title: none | text: text"


def test_validate_accepts_unit_vectors():
    validate_vectors([_unit(768), _unit(768, 5)], expected=2, dimensions=768)


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ([_unit(768)], "expected 2 vectors"),
        ([_unit(768), _unit(767)], "767 values"),
        ([_unit(768), [math.nan] + [0.0] * 767], "non-finite"),
        ([_unit(768), [2.0] + [0.0] * 767], "not unit length"),
    ],
)
def test_validate_rejects_bad_vectors(vectors, message):
    with pytest.raises(EmbeddingError, match=message):
        validate_vectors(vectors, expected=2, dimensions=768)


def test_cosine():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 0.0])
