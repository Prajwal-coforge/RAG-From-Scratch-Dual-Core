import json

import pytest

import app.pipeline as pipeline
import app.triage as triage_module
from app.triage import applicability_rules, missing_facts, triage


def test_policy_id_or_issuer_name_decides_the_context():
    assert triage("What does AP-SEC-003 section 2 say?")["corpus_id"] == "airport-generated"
    routed = triage("What is the SkyWings checked baggage allowance?")
    assert routed["corpus_id"] == "skywings-baggage" and routed["snapshot_id"] == "imported:skywings-baggage"
    assert routed["basis"] == "named in the question"


def test_distinctive_vocabulary_routes_only_when_it_dominates():
    routed = triage("What are the domestic and international per diem rates for pilots?")
    assert routed["corpus_id"] == "aethersky-compensation" and "diem" in routed["signals"]["distinctive_terms"]["aethersky-compensation"]
    unclear = triage("What is the checked bag weight limit?")
    assert unclear["status"] == "needs_clarification" and unclear["route"] == "clarify"
    assert len(unclear["options"]) == 4 and "Which policy context" in unclear["follow_up_questions"][0]


def test_two_issuers_are_never_blended():
    result = triage("Under AP-BAG-001, what does SkyWings charge for overweight bags?")
    assert result["status"] == "needs_clarification" and "more than one issuer" in result["reason"]
    assert {o["corpus_id"] for o in result["options"]} == {"airport-generated", "skywings-baggage"}


def test_selected_context_is_kept_unless_the_question_is_about_another_issuer():
    kept = triage("What happens to a bag that weighs more than 32 kg?", selected="skywings-baggage")
    assert kept["status"] == "routed" and kept["basis"] == "selected by the caller"
    mismatch = triage("What is the per diem rate for pilots?", selected="skywings-baggage")
    assert mismatch["status"] == "needs_clarification" and "AetherSky" in mismatch["reason"]
    named = triage("What does AP-INC-002 require?", selected="aethersky-compensation")
    assert named["status"] == "needs_clarification"
    with pytest.raises(ValueError):
        triage("anything", selected="no-such-corpus")


def test_cross_policy_questions_use_graph_rerank():
    cross = triage("To whom is an operational incident first reported, and where does the incident policy send staff for baggage escalation?")
    assert cross["route"] == "cross_policy" and cross["mode"] == "graph_rerank"
    assert cross["policies"] == ["AP-BAG-001", "AP-INC-002"]
    direct = triage("What does AP-SEC-003 section 2 say?")
    assert direct["route"] == "direct_lookup" and direct["mode"] == "hybrid_rerank"


def hit(heading):
    return {"heading_path": heading, "document_title": "t"}


def test_missing_applicability_facts_come_from_the_top_section():
    [fact] = missing_facts("skywings-baggage", "What is the checked baggage allowance?", hit("4 Checked Baggage Allowance"))
    assert fact["fact"] == "travel_class" and "First Class" in fact["values"]
    assert missing_facts("skywings-baggage", "What is the Economy checked baggage allowance?", hit("4 Checked Baggage Allowance")) == []
    assert missing_facts("skywings-baggage", "What is the maximum weight?", hit("5 Excess Baggage Fees")) == []
    [rank_only] = missing_facts("aethersky-compensation", "What is the hourly pay for a Captain?", hit("2.1 Base Pay"))
    assert rank_only["fact"] == "aircraft_type"
    assert missing_facts("airport-generated", "Who approves?", hit("4 Approval Procedure")) == []
    assert missing_facts("skywings-baggage", "anything", None) == []


def test_applicability_table_is_checked_against_the_source(tmp_path, monkeypatch):
    table = json.loads(triage_module.APPLICABILITY.read_text())
    table["corpora"]["skywings-baggage"][0]["section_mentions"]["4"].append("Premium Economy")
    bad = tmp_path / "applicability.json"
    bad.write_text(json.dumps(table))
    monkeypatch.setattr(triage_module, "APPLICABILITY", bad)
    applicability_rules.cache_clear()
    try:
        with pytest.raises(ValueError, match="Premium Economy"):
            applicability_rules()
    finally:
        applicability_rules.cache_clear()


class NoEmbedder:
    tokenizer = None


class CountingEmbedder:
    class tokenizer:
        name = "test"

        @staticmethod
        def count(text):
            return max(1, len(text.split()))


def no_chat(*args, **kwargs):
    raise AssertionError("generation must not run")


def test_unclear_issuer_is_searched_without_asking_for_a_context(monkeypatch):
    seen = {}

    def fake_retrieve(session, index, embedder, question, snapshot_id, **kwargs):
        seen["snapshot_id"] = snapshot_id
        seen["mode"] = kwargs["mode"]
        return {
            "mode": kwargs["mode"],
            "corpus_id": "skywings-baggage",
            "snapshot_id": snapshot_id,
            "index_generation_id": "gen-test",
            "as_of": "2026-01-01",
            "include_history": False,
            "question": question,
            "timing_ms": 1.0,
            "stage_timing_ms": {},
            "search": {"method": "test", "eligible": 1, "generation_chunks": 1, "excluded": [], "stages": {}},
            "hits": [{
                "rank": 1, "chunk_id": "c1", "document_version_id": "skywings-baggage:doc",
                "document_title": "SkyWings", "corpus_id": "skywings-baggage", "policy_id": "SKY",
                "version": "1", "section_id": "s5", "heading_path": "5 Excess Baggage Fees",
                "text": "No single piece over 32 kg will be accepted as checked baggage.",
                "publication_status": "active", "effective_from": None, "effective_to": None,
                "source_spans": [[0, 10]], "similarity": 0.5, "signals": {"rerank_score": 1.0},
                "context": {"mandatory": [], "parent": []},
            }],
            "context_chunks": {},
            "candidates": [],
        }

    def fake_route(_question):
        return {
            "status": "routed", "route": "model", "basis": "test",
            "corpus_ids": ["skywings-baggage"], "snapshot_ids": ["imported:skywings-baggage"], "raw": "{}",
        }

    def fake_chat(messages, **kwargs):
        return {"response": {"message": {"content": "INSUFFICIENT_EVIDENCE: not in the passage"}}, "model_blob_digest": "x"}

    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    report = pipeline.ask_question(
        None, "idx", CountingEmbedder(), "What is the checked bag weight limit?",
        reranker_for=lambda mode: None, router_fn=fake_route, chat_fn=fake_chat,
    )
    assert seen["snapshot_id"] == "imported:skywings-baggage"
    assert "policy context" not in report["answer"]["answer"].lower()
    assert report["retrieval"]["hits"]


def test_several_contexts_are_searched_and_not_blended_into_a_menu(monkeypatch):
    seen = []

    def fake_retrieve(session, index, embedder, question, snapshot_id, **kwargs):
        seen.append(snapshot_id)
        corpus = "airport-generated" if snapshot_id == "clean" else "skywings-baggage"
        return {
            "mode": kwargs["mode"], "corpus_id": corpus, "snapshot_id": snapshot_id,
            "index_generation_id": f"gen-{snapshot_id}", "as_of": "2026-01-01", "include_history": False,
            "question": question, "timing_ms": 1.0, "stage_timing_ms": {},
            "search": {"method": "test", "eligible": 1, "generation_chunks": 1, "excluded": [], "stages": {}},
            "hits": [{
                "rank": 1, "chunk_id": snapshot_id, "document_version_id": snapshot_id,
                "document_title": corpus, "corpus_id": corpus, "policy_id": "P", "version": "1",
                "section_id": "s", "heading_path": "1 Purpose", "text": f"Rule from {corpus}.",
                "publication_status": "active", "effective_from": None, "effective_to": None,
                "source_spans": [[0, 4]], "similarity": 0.4, "signals": {"rerank_score": 2.0 if corpus == "skywings-baggage" else 1.0},
                "context": {"mandatory": [], "parent": []},
            }],
            "context_chunks": {}, "candidates": [],
        }

    def fake_route(_question):
        return {
            "status": "routed", "route": "model", "basis": "test",
            "corpus_ids": ["airport-generated", "skywings-baggage"],
            "snapshot_ids": ["clean", "imported:skywings-baggage"], "raw": "{}",
        }

    def fake_chat(messages, **kwargs):
        assert "more than one policy issuer" in messages[1]["content"]
        return {"response": {"message": {"content": "INSUFFICIENT_EVIDENCE: see the passages"}}, "model_blob_digest": "x"}

    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    report = pipeline.ask_question(
        None, "idx", CountingEmbedder(), "What is the baggage limit for every airline?",
        reranker_for=lambda mode: None, router_fn=fake_route, chat_fn=fake_chat,
    )
    assert seen == ["clean", "imported:skywings-baggage"]
    assert [hit["chunk_id"] for hit in report["retrieval"]["hits"]] == ["imported:skywings-baggage", "clean"]
    assert "Which policy context" not in report["answer"]["answer"]


def test_missing_fact_stops_before_generation(monkeypatch):
    retrieval = {
        "mode": "hybrid_rerank", "corpus_id": "skywings-baggage", "snapshot_id": "imported:skywings-baggage",
        "index_generation_id": "gen-test", "hits": [hit("4 Checked Baggage Allowance")],
    }
    seen = {}

    def fake_retrieve(session, index, embedder, question, snapshot_id, **kwargs):
        seen.update(snapshot_id=snapshot_id, **kwargs)
        return retrieval

    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    report = pipeline.ask_question(None, "idx", NoEmbedder(), "What is the SkyWings checked baggage allowance?",
                                   reranker_for=lambda m: None, chat_fn=no_chat)
    answer = report["answer"]
    assert seen["snapshot_id"] == "imported:skywings-baggage" and seen["mode"] == "hybrid_rerank"
    assert answer["status"] == "needs_clarification" and answer["generation"] is None
    assert answer["missing_facts"][0]["fact"] == "travel_class" and "travel class" in answer["follow_up_questions"][0]
