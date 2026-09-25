"""Live graph links and graph_rerank against Memgraph and the pinned models."""

import pytest

from app.doctor import load_lock
from app.embedder import embedder_from_lock
from app.ingest import build_plan, connect, ingest
from app.rerank import reranker_from_lock
from app.retrieve import MAX_GRAPH_CANDIDATES, MAX_RERANK_CANDIDATES, retrieve
from app.sources import load_snapshot

pytestmark = pytest.mark.live
QUESTION = "When a restricted item is found in a bag, what must happen and who approves it?"


@pytest.fixture(scope="module")
def embedder():
    return embedder_from_lock(load_lock())


@pytest.fixture(scope="module")
def published(embedder):
    return ingest("clean", embedder=embedder, log=lambda _line: None)


def run(query, **params):
    driver, _index = connect()
    try:
        with driver.session() as session:
            return session.run(query, **params).data()
    finally:
        driver.close()


def test_stored_edges_match_the_plan_and_carry_provenance(embedder, published):
    gen = published["generation_id"]
    plan = build_plan(load_snapshot("clean"), embedder)
    stored = {r["t"]: r["n"] for r in run("MATCH ()-[r {generation_id: $g}]->() RETURN type(r) AS t, count(*) AS n", g=gen)}
    expected = plan.graph.counts()
    for kind in ("REFERENCES", "APPLIES_TO_ROLE", "MAPS_TO_CONTROL", "OWNED_BY"):
        assert stored.get(kind, 0) == expected.get(kind, 0)
    texts = {d.document_version_id: d.text for d in load_snapshot("clean").documents}
    edges = run(
        "MATCH (:Section {generation_id: $g})-[r]->() WHERE type(r) IN ['REFERENCES', 'APPLIES_TO_ROLE', 'MAPS_TO_CONTROL'] "
        "RETURN properties(r) AS p",
        g=gen,
    )
    assert edges
    for edge in (e["p"] for e in edges):
        assert edge["validation_status"] in ("validated", "exact-name-match", "reviewed-anchor")
        assert texts[edge["document_version_id"]][edge["source_start"] : edge["source_end"]].strip() == edge["evidence"]


def test_graph_rerank_reports_bounded_paths_from_validated_edges(embedder, published):
    reranker = reranker_from_lock(load_lock())
    driver, index = connect()
    try:
        with driver.session() as session:
            result = retrieve(session, index, embedder, QUESTION, "clean", mode="graph_rerank", reranker=reranker)
    finally:
        driver.close()
    graph = result["search"]["stages"]["graph"]
    assert graph["hops"] == 1 and graph["edges_in_generation"] == 6
    assert len(graph["added"]) <= MAX_GRAPH_CANDIDATES
    assert len(result["candidates"]) <= MAX_RERANK_CANDIDATES
    assert result["search"]["stages"]["rerank"]["candidates"] == len(result["candidates"])
    paths = [p for c in result["candidates"] for p in c["signals"].get("graph_paths", [])]
    assert paths and all(p["validation_status"] == "validated" and p["hops"] == 1 for p in paths)
    assert all(p["target_policy_id"] in p["evidence"] for p in paths)
