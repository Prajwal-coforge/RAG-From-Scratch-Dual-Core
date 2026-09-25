import pytest

from app.answer import answer_question, build_evidence
from app.keyword import EXACT_BOOST, BM25Index, exact_terms, tokenize
from app.rerank import Reranker
from app.retrieve import RRF_K, Pool, linked_context, rank_candidates, rrf_fuse


def chunk(cid, text, *, title="AP-BAG-001 v2 Staff Baggage", heading="4 Escalation", section="s4", start=0, **extra):
    return {
        "chunk_id": cid,
        "document_version_id": "airport-generated:AP-BAG-001:v2",
        "document_title": title,
        "corpus_id": "airport-generated",
        "policy_id": "AP-BAG-001",
        "version": "2",
        "publication_status": "active",
        "effective_from": "2025-07-01",
        "effective_to": None,
        "section_id": section,
        "heading_path": heading,
        "text": text,
        "source_spans": [[start, start + len(text)]],
        "source_start": start,
        "continuation_of": None,
        "exception_refs": [],
        **extra,
    }


def pool_of(chunks):
    by_id = {c["chunk_id"]: c for c in chunks}
    return Pool({"id": "gen-test", "chunk_count": len(chunks)}, by_id, [c["chunk_id"] for c in chunks], [])


def test_identifiers_sections_and_units_are_single_terms():
    terms = [(t.text, t.kind) for t in tokenize("AP-BAG-001, section 4.2, and 23 kg; $3.25 per hour; must not be handled")]
    assert ("ap-bag-001", "ident") in terms and ("§4.2", "section") in terms and ("23kg", "unit") in terms
    assert ("$3.25", "money") in terms and ("not", "word") in terms
    assert tokenize("15 grams")[0].text == tokenize("15 g")[0].text == "15g"
    assert tokenize("10 minutes")[0].text == "10min"
    assert tokenize("see 4.2")[1].text == "§4.2"
    assert exact_terms('What does AP-SEC-003 "make-up area" say?') == ["ap-sec-003", '"make-up area"']


def test_bm25_records_score_boost_and_rank_and_boosts_the_exact_identifier():
    chunks = [
        chunk("a", "Staff must escalate a leaking bag.", title="AP-BAG-001 v2 Staff Baggage"),
        chunk("b", "Staff must escalate a leaking bag.", title="AP-SEC-003 v1 Screening"),
        chunk("c", "Records are kept for two years.", title="AP-INC-002 v1 Incidents"),
    ]
    results = BM25Index(chunks).search("What does AP-SEC-003 say about a leaking bag?", 10)
    assert [r["chunk_id"] for r in results[:2]] == ["b", "a"]
    top = results[0]
    assert top["exact_terms"] == ["ap-sec-003"] and top["boost"] == EXACT_BOOST
    assert top["score"] == pytest.approx(top["bm25"] + top["boost"]) and top["rank"] == 1
    assert all({"bm25", "boost", "rank", "score", "exact_terms"} <= r.keys() for r in results)


def test_heading_number_matches_a_section_reference():
    chunks = [chunk("a", "Make-up area rules.", heading="2 Make-up Area"), chunk("b", "Other text.", heading="5 Reporting")]
    results = BM25Index(chunks).search("section 2", 10)
    assert results[0]["chunk_id"] == "a" and results[0]["exact_terms"] == ["§2"]


def test_rrf_uses_ranks_dedupes_by_chunk_and_breaks_ties_by_id():
    vector = [{"chunk_id": "x", "rank": 1}, {"chunk_id": "y", "rank": 2}]
    keyword = [{"chunk_id": "y", "rank": 1}, {"chunk_id": "z", "rank": 2}]
    fused = rrf_fuse(vector, keyword)
    assert [e["chunk_id"] for e in fused] == ["y", "x", "z"]
    assert fused[0]["rrf"] == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert fused[0]["rrf_parts"] == {"vector": pytest.approx(1 / 62), "keyword": pytest.approx(1 / 61)}
    tie = rrf_fuse([{"chunk_id": "b", "rank": 1}], [{"chunk_id": "a", "rank": 1}])
    assert [e["chunk_id"] for e in tie] == ["a", "b"]


class FakeCross:
    """Scores a pair by how many question words appear in the passage."""

    class _Tok:
        def __call__(self, first, second=None, add_special_tokens=True, truncation=False):
            ids = first.split() + (second.split() if second else [])
            return {"input_ids": ids + (["[S]"] * 3 if add_special_tokens else [])}

    tokenizer = _Tok()

    def predict(self, pairs, **kwargs):
        self.pairs = pairs
        return [float(sum(w in p.lower() for w in q.lower().split())) for q, p in pairs]


def test_hybrid_rerank_records_every_signal_and_the_rank_change():
    chunks = [
        chunk("a", "Escalate a leaking bag within 10 minutes."),
        chunk("b", "Records are kept for two years."),
        chunk("c", "Report the leaking bag to the supervisor."),
    ]
    pool = pool_of(chunks)
    vector = [
        {"chunk_id": "b", "rank": 1, "similarity": 0.9, "exact_cosine": 0.9},
        {"chunk_id": "a", "rank": 2, "similarity": 0.8, "exact_cosine": 0.8},
        {"chunk_id": "c", "rank": 3, "similarity": 0.7, "exact_cosine": 0.7},
    ]
    reranker = Reranker("fake", "0" * 40, 512, model=FakeCross())
    question = "escalate leaking bag within minutes"
    candidates, stages = rank_candidates(pool, question, "hybrid_rerank", vector=vector, reranker=reranker)
    assert candidates[0]["chunk_id"] == "a"
    signals = candidates[0]["signals"]
    assert {"vector_rank", "similarity", "keyword_rank", "bm25", "boost", "rrf", "rerank_score", "rank_before_rerank"} <= signals.keys()
    assert stages["rrf"]["k"] == RRF_K and stages["rerank"]["candidates"] == 3
    vector_only, _ = rank_candidates(pool, question, "vector", vector=vector)
    assert [c["chunk_id"] for c in vector_only] == ["b", "a", "c"]


def test_overlong_rerank_pair_is_windowed_not_truncated():
    sentences = " ".join(f"Sentence {i} about the baggage rule." for i in range(120))
    long = chunk("long", sentences + " Exception: a supervisor may extend it.")
    reranker = Reranker("fake", "0" * 40, 512, model=FakeCross())
    pairs = reranker.pairs_for("may a supervisor extend it", long)
    assert len(pairs) > 1
    assert all(reranker.tokenizer.pair(q, p) <= 512 for q, p in pairs)
    assert "Exception: a supervisor may extend it." in pairs[-1][1]
    [record] = reranker.score("may a supervisor extend it", [long])
    assert record["windows"] == len(pairs) and record["pair_tokens"] <= 512


def test_linked_context_follows_continuations_and_exceptions():
    rule = chunk("s4-a", "Escalate within 10 minutes, except as below.", start=0, exception_refs=["not-a-chunk-id"])
    exception = chunk("s4-b", "Exception: a supervisor may extend it.", start=50)
    other = chunk("s4-c", "Record the escalation.", start=100)
    elsewhere = chunk("s5-a", "Unrelated.", section="s5", start=200)
    pool = pool_of([rule, exception, other, elsewhere])
    assert linked_context(pool, "s4-a") == {"mandatory": ["s4-b"], "parent": ["s4-c"]}
    part2 = chunk("s4-d", "second half", start=150, continuation_of="s4-c")
    pool = pool_of([rule, exception, other, part2])
    assert linked_context(pool, "s4-d")["mandatory"] == ["s4-c"]


class Words:
    name = "words"

    def count(self, text):
        return len(text.split())


def test_mandatory_context_travels_with_its_hit_and_parent_fills_remaining_budget():
    rule = {**chunk("r", "rule " * 20), "context": {"mandatory": ["e"], "parent": ["p"]}}
    context = {"e": chunk("e", "exception " * 20), "p": chunk("p", "parent " * 20)}
    used, omitted, _total, shortfall = build_evidence([rule], Words(), budget=200, context=context)
    assert [(u["chunk_id"], u["role"]) for u in used] == [("r", "retrieved"), ("e", "mandatory_context"), ("p", "parent_context")]
    assert shortfall is None and not omitted
    used, omitted, _total, _ = build_evidence([rule], Words(), budget=80, context=context)
    assert [u["chunk_id"] for u in used] == ["r", "e"] and omitted[0]["chunk_id"] == "p"


def test_top_hit_whose_mandatory_context_does_not_fit_is_insufficient_evidence():
    rule = {**chunk("r", "rule " * 2000), "context": {"mandatory": ["e"], "parent": []}}
    retrieval = {
        "question": "q", "mode": "hybrid", "corpus_id": "airport-generated", "snapshot_id": "clean",
        "index_generation_id": "gen-test", "as_of": "2025-08-01", "hits": [rule],
        "context_chunks": {"e": chunk("e", "exception " * 2000)},
    }

    def no_chat(*args, **kwargs):
        raise AssertionError("generation must not run")

    result = answer_question(retrieval, Words(), chat_fn=no_chat, sources={})
    assert result["status"] == "insufficient_evidence" and result["generation"] is None
    assert "cannot be used whole" in result["answer"]
