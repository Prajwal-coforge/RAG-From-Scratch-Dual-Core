import pytest

from app.smoke import INDEX, LABEL, NAMESPACE, QUERIES, TEXTS, run_smoke


def test_smoke_texts_are_distinct_and_namespaced():
    assert len(TEXTS) == 2
    assert len({item.id for item in TEXTS}) == 2
    assert all(item.id.startswith(f"{NAMESPACE}:") for item in TEXTS)
    assert {query.expected_id for query in QUERIES} == {item.id for item in TEXTS}


def test_smoke_does_not_touch_the_production_index():
    assert LABEL != "Chunk"
    assert INDEX != "chunk_embedding"


@pytest.mark.live
def test_two_text_loop_against_real_ollama_and_memgraph():
    report = run_smoke(log=lambda line: None)
    assert report["ok"], report["queries"]
    assert report["index"]["size_after_each_step"] == [0, 1, 2]
    assert report["index"]["dimension"] == 768
    assert report["production_index_size"] == 0
    for result in report["queries"]:
        assert result["index_hits"][0]["id"] == result["expected_id"]
        assert result["margin"] > 0
