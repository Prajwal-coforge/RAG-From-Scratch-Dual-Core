from app.evaluation.cases import Case, Clause, Fact
from app.evaluation.judge import parse_verdict
from app.evaluation.metrics import citation_report, covered_clauses, fact_report, percentile, set_recall, summarize

DOC = "airport-generated:AP-BAG-001:v2"
CLAUSES = {
    "A": Clause("A", DOC, "4", "Escalate within 10 minutes.", 100, 127),
    "B": Clause("B", DOC, "4", "Tell the supervisor.", 200, 220),
    "C": Clause("C", "other:doc:v1", "1", "Other.", 100, 106),
}


def case(expected="answered", sets=(("A", "B"),), required=(), prohibited=()):
    return Case("T-1", "dev", "generated", "airport-generated", "clean", "2025-08-01", False, "q", expected,
                sets, tuple(required), tuple(prohibited), "r")


def test_a_clause_is_covered_only_by_a_span_containing_the_whole_anchor():
    whole = {"document_version_id": DOC, "source_spans": [[90, 130]]}
    partial = {"document_version_id": DOC, "source_spans": [[110, 230]]}
    joined = {"document_version_id": DOC, "source_spans": [[90, 115], [115, 230]]}
    assert covered_clauses([whole], CLAUSES) == {"A"}
    assert covered_clauses([partial], CLAUSES) == {"B"}
    assert covered_clauses([joined], CLAUSES) == {"A", "B"}


def test_overlapping_chunks_count_a_clause_once_and_the_best_set_wins():
    assert set_recall({"A"}, (("A", "B"),))["recall"] == 0.5
    best = set_recall({"A"}, (("A", "B"), ("A",)))
    assert best["recall"] == 1.0 and best["best_set"] == ["A"]
    assert set_recall({"A"}, ()) is None


def test_facts_count_only_for_an_answered_status_and_prohibited_facts_fail_the_case():
    required = [Fact("ten", (r"\b10 minutes\b",))]
    prohibited = [Fact("thirty", (r"\b30 minutes\b",))]
    good = {"status": "answered", "answer": "Within 10 minutes [1]."}
    assert fact_report(case(required=required, prohibited=prohibited), good)["passed"]
    both = {"status": "answered", "answer": "Within 10 minutes, formerly 30 minutes [1]."}
    report = fact_report(case(required=required, prohibited=prohibited), both)
    assert report["fact_accuracy"] == 1.0 and not report["passed"]
    withheld = {"status": "unavailable", "answer": "withheld"}
    assert fact_report(case(required=required), withheld)["fact_accuracy"] == 0.0
    abstain = {"status": "insufficient_evidence", "answer": "INSUFFICIENT_EVIDENCE: no list"}
    assert fact_report(case(expected="insufficient_evidence", sets=()), abstain)["passed"]


def test_citation_validity_needs_no_invented_ids_and_resolved_citations():
    assert citation_report({"generation": None})["valid"] is None
    ok = {"generation": {}, "status": "answered", "invented_citation_ids": [], "citations": [{"resolved": True}]}
    assert citation_report(ok)["valid"] is True
    invented = {**ok, "invented_citation_ids": [7]}
    assert citation_report(invented)["valid"] is False


def test_percentile_is_nearest_rank():
    assert percentile([5, 1, 3, 2, 4], 50) == 3 and percentile([5, 1, 3, 2, 4], 95) == 5 and percentile([], 50) is None


def test_summary_macro_averages_answerable_cases():
    def outcome(recall, passed, expected="answered"):
        r = None if recall is None else {"recall": recall}
        return {
            "expected_status": expected, "eligible_chunks": 20,
            "recall": {"candidate_recall_at_20": r, "recall_at_3": r, "recall_at_5": r},
            "facts": {"fact_accuracy": 1.0 if passed else 0.0, "passed": passed, "status_ok": True, "prohibited": {}},
            "citations": {"generated": True, "valid": True, "uncited": False},
            "latency_ms": {"total": 10.0},
        }

    s = summarize([outcome(1.0, True), outcome(0.5, False), outcome(None, True, "insufficient_evidence")])
    assert s["recall_at_5"] == 0.75 and s["fact_accuracy"] == 0.5 and s["case_pass_rate"] == 2 / 3
    assert s["citation_validity"] == 1.0 and s["latency_ms"]["runs"] == 3


def test_judge_verdict_parsing_is_strict():
    assert parse_verdict('{"verdict": "Supported", "reason": "stated"}') == ("supported", "stated")
    assert parse_verdict('text {"verdict": "unsupported", "reason": "x"} more')[0] == "unsupported"
    assert parse_verdict("maybe")[0] == "unparsed"
