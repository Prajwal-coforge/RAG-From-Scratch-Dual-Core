import json

import pytest

from app.chunking.chunk import ChunkConfig
from app.embedder import InputTooLong
from app.ingest import IngestError, build_plan, check_coverage, embed_plan
from app.retrieve import RetrievalRefused, check_compatible
from app.sources import available_snapshots, load_snapshot
from app.state import State


def test_every_snapshot_is_fully_covered_by_chunk_spans(make_embedder):
    embedder = make_embedder()
    for snapshot_id in available_snapshots():
        plan = build_plan(load_snapshot(snapshot_id), embedder)
        assert plan.chunks, snapshot_id
        for doc in plan.documents:
            for chunk in doc.chunks:
                pieces = [doc.source.text[s:e] for s, e in chunk.spans]
                assert all(piece.strip() and piece.strip() in chunk.text for piece in pieces)
                assert chunk.embedding_input.startswith(f"title: {doc.source.document_title} / ")


def test_coverage_check_catches_a_dropped_span(make_embedder):
    plan = build_plan(load_snapshot("clean"), make_embedder())
    doc = plan.documents[0]
    with pytest.raises(IngestError, match="not covered"):
        check_coverage(doc.source, doc.sections, doc.chunks[1:])


def test_over_limit_input_is_refused_before_anything_is_embedded(make_embedder):
    embedder = make_embedder(max_seq_length=40)
    with pytest.raises(InputTooLong):
        build_plan(load_snapshot("clean"), embedder, config=ChunkConfig(target_tokens=30, max_tokens=38, overlap_tokens=0))


def test_generation_id_is_stable_and_changes_with_any_fingerprint_input(make_embedder):
    snapshot = load_snapshot("clean")
    base = build_plan(snapshot, make_embedder()).generation_id
    assert build_plan(load_snapshot("clean"), make_embedder()).generation_id == base
    assert build_plan(snapshot, make_embedder(revision="1" * 40)).generation_id != base
    assert build_plan(snapshot, make_embedder(), config=ChunkConfig(target_tokens=200)).generation_id != base
    assert build_plan(snapshot, make_embedder(), profile="evaluation").generation_id != base
    assert build_plan(load_snapshot("duplicate"), make_embedder()).generation_id != base


def test_embedding_cache_is_keyed_by_input_and_model(tmp_path, make_embedder):
    state = State(tmp_path / "state.sqlite")
    embedder = make_embedder()
    plan = build_plan(load_snapshot("clean"), embedder)
    lines = []
    first = embed_plan(plan, embedder, state, lines.append)
    again = embed_plan(plan, embedder, state, lines.append)
    assert first == again
    assert "0 cached" in lines[0] and f"{len(plan.chunks)} cached" in lines[1]
    other = make_embedder(revision="1" * 40)
    embed_plan(build_plan(load_snapshot("clean"), other), other, state, lines.append)
    assert "0 cached" in lines[2]
    state.close()


def test_query_with_a_different_embedder_is_refused(make_embedder):
    built = make_embedder()
    generation = {"id": "gen-x", "embedder": json.dumps(built.identity)}
    check_compatible(generation, built)
    with pytest.raises(RetrievalRefused, match="Re-ingest"):
        check_compatible(generation, make_embedder(revision="1" * 40))
    with pytest.raises(RetrievalRefused):
        check_compatible(generation, make_embedder(model_id="other/model"))
