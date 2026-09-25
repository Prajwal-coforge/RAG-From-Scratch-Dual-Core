"""Live ingestion and basic RAG against the real embedder, Memgraph, and Ollama."""

import pytest

from app.chunking.chunk import ChunkConfig
from app.doctor import load_lock
from app.embedder import embedder_from_lock
from app.ingest import GraphStore, IngestError, PublicationRefused, connect, ingest, rollback
from app.retrieve import retrieve

pytestmark = pytest.mark.live
QUESTION = "A baggage handler finds a leaking checked bag in the make-up area. Who must they escalate it to, and how quickly?"
ALTERNATE = ChunkConfig(target_tokens=200)


def quiet(_line):
    pass


@pytest.fixture(scope="module")
def embedder():
    return embedder_from_lock(load_lock())


@pytest.fixture(scope="module")
def published(embedder):
    return ingest("clean", embedder=embedder, log=quiet)


def pointer(snapshot_id):
    driver, index = connect()
    try:
        with driver.session() as session:
            return GraphStore(session, index).pointer(snapshot_id)
    finally:
        driver.close()


def ask(embedder, question, snapshot_id, **kwargs):
    driver, index = connect()
    try:
        with driver.session() as session:
            return retrieve(session, index, embedder, question, snapshot_id, **kwargs)
    finally:
        driver.close()


def test_reingest_is_idempotent(embedder, published):
    again = ingest("clean", embedder=embedder, log=quiet)
    assert again["status"] == "unchanged"
    assert again["generation_id"] == published["generation_id"]


def test_failed_build_leaves_the_published_generation_serving(embedder, published):
    before = pointer("clean")
    with pytest.raises(IngestError, match="injected"):
        ingest("clean", embedder=embedder, config=ALTERNATE, fail_after_write=True, log=quiet)
    assert pointer("clean") == before
    driver, index = connect()
    try:
        with driver.session() as session:
            failed = session.run(
                "MATCH (g:IndexGeneration {status: 'failed'}) OPTIONAL MATCH (c:Chunk {generation_id: g.id}) "
                "RETURN g.id AS id, count(c) AS chunks"
            ).data()
    finally:
        driver.close()
    assert failed and all(row["chunks"] == 0 for row in failed)
    result = ask(embedder, QUESTION, "clean")
    assert result["index_generation_id"] == before["current"]


def test_publish_then_roll_back(embedder, published):
    original = pointer("clean")["current"]
    report = ingest("clean", embedder=embedder, config=ALTERNATE, log=quiet)
    assert report["status"] == "published"
    moved = pointer("clean")
    assert (moved["current"], moved["previous"]) == (report["generation_id"], original)
    rollback("clean", log=quiet)
    assert pointer("clean")["current"] == original


def test_damaged_fixture_needs_the_evaluation_profile(embedder):
    with pytest.raises(PublicationRefused):
        ingest("dirty-stale", embedder=embedder, log=quiet)


def test_vector_retrieval_finds_the_current_rule_and_agrees_with_exact_cosine(embedder, published):
    result = ask(embedder, QUESTION, "clean")
    top = result["hits"][0]
    assert top["document_version_id"] == "airport-generated:AP-BAG-001:v2"
    assert "10 minutes" in top["text"]
    assert result["exact_check"]["top_k_agrees"] and result["exact_check"]["scores_agree"]


def test_superseded_version_is_excluded_unless_history_is_requested(embedder):
    ingest("duplicate", embedder=embedder, log=quiet)
    current = ask(embedder, QUESTION, "duplicate")
    assert all(hit["version"] == "2" for hit in current["hits"] if hit["policy_id"] == "AP-BAG-001")
    ingest("historical", embedder=embedder, log=quiet)
    past = ask(embedder, QUESTION, "historical", as_of="2025-03-15", include_history=True)
    assert past["hits"][0]["document_version_id"] == "airport-generated:AP-BAG-001:v1"


def test_basic_rag_answer_is_cited_and_resolvable(embedder, published):
    from app.answer import answer_question

    result = answer_question(ask(embedder, QUESTION, "clean"), embedder.tokenizer)
    assert result["status"] == "answered", result
    assert "10 minutes" in result["answer"]
    assert result["citations"] and all(c["resolved"] for c in result["citations"])
    assert any(c["document_version_id"] == "airport-generated:AP-BAG-001:v2" for c in result["citations"])


def test_missing_base_rate_is_reported_not_invented(embedder):
    from app.answer import answer_question

    ingest("imported:aethersky-compensation", embedder=embedder, log=quiet)
    retrieval = ask(embedder, "What is the exact hourly base pay rate for a first officer?", "imported:aethersky-compensation")
    result = answer_question(retrieval, embedder.tokenizer)
    assert result["status"] == "insufficient_evidence", result["generation"]["raw_answer"]
