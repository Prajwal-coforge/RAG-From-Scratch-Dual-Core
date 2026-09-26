"""Fixed evaluation cases on the generated corpus, run live through the full pipeline."""

import pytest

from app.answer import answer_question
from app.doctor import load_lock
from app.embedder import embedder_from_lock
from app.evaluation.cases import load_cases, load_clauses
from app.evaluation.metrics import citation_report, fact_report, recall_report
from app.evaluation.needle import NEEDLE_ID, run_needle
from app.ingest import connect, ingest
from app.rerank import reranker_from_lock
from app.retrieve import retrieve
from app.sources import load_snapshot

pytestmark = pytest.mark.live
MODE = "hybrid_rerank"
CLAUSES = load_clauses()
GENERATED = [c for split in ("dev", "heldout") for c in load_cases(split, CLAUSES) if c.corpus_kind == "generated"]


@pytest.fixture(scope="module")
def models():
    lock = load_lock()
    return embedder_from_lock(lock), reranker_from_lock(lock)


@pytest.fixture(scope="module")
def published(models):
    embedder, _ = models
    for snapshot_id in sorted({c.snapshot_id for c in GENERATED}):
        ingest(snapshot_id, embedder=embedder, log=lambda _line: None)


def run(models, case, mode=MODE):
    embedder, reranker = models
    driver, index = connect()
    try:
        with driver.session() as session:
            return retrieve(
                session, index, embedder, case.question, case.snapshot_id,
                as_of=case.as_of, include_history=case.include_history, mode=mode, reranker=reranker,
            )
    finally:
        driver.close()


def test_at_least_eight_generated_cases():
    assert len(GENERATED) >= 8


@pytest.mark.parametrize("case", GENERATED, ids=[c.case_id for c in GENERATED])
def test_generated_case_passes(models, published, case):
    embedder, _ = models
    retrieval = run(models, case)
    sources = {d.document_version_id: d.text for d in load_snapshot(case.snapshot_id).documents}
    result = answer_question(retrieval, embedder.tokenizer, sources=sources)
    facts = fact_report(case, result)
    assert facts["passed"], {"facts": facts, "answer": result["answer"]}
    citations = citation_report(result)
    assert citations["valid"] in (True, None), citations
    recall = recall_report(case, retrieval["candidates"], retrieval["hits"], CLAUSES)["recall_at_5"]
    assert recall is None or recall["recall"] == 1.0, recall


def test_hybrid_finds_the_section_lookup_that_vector_misses(models, published):
    [demo] = [c for c in GENERATED if c.case_id == "D-G07"]
    vector = recall_report(demo, [], run(models, demo, "vector")["hits"], CLAUSES)["recall_at_5"]
    hybrid = recall_report(demo, [], run(models, demo, "hybrid")["hits"], CLAUSES)["recall_at_5"]
    assert vector["recall"] == 0.0 and hybrid["recall"] == 1.0


def test_needle_is_found_in_an_isolated_index_that_is_cleaned_up(models, published):
    embedder, reranker = models
    driver, _index = connect()
    try:
        with driver.session() as session:
            report = run_needle(session, load_lock(), embedder, reranker)
    finally:
        driver.close()
    assert report["isolation"]["ok"], report["isolation"]
    by_code = {r["mode"]: r["needle_rank"] for r in report["results"] if r["query"] == "by_code"}
    assert by_code["keyword"] == 1 and by_code["hybrid"] == 1, by_code
    assert report["needle"]["chunk_id"] == NEEDLE_ID
