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


def no_chat(*args, **kwargs):
    raise AssertionError("generation must not run")


def test_unclear_issuer_is_answered_with_a_clarification_before_retrieval(monkeypatch):
    monkeypatch.setattr(pipeline, "retrieve", lambda *a, **k: pytest.fail("retrieval must not run"))
    report = pipeline.ask_question(None, "idx", NoEmbedder(), "What is the checked bag weight limit?", reranker_for=lambda m: None)
    assert report["retrieval"] is None and report["answer"]["status"] == "needs_clarification"
    assert report["answer"]["follow_up_questions"] and report["answer"]["citations"] == []


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
