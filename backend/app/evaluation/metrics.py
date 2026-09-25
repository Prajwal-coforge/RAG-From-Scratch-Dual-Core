"""Deterministic evaluation metrics.

Recall is measured on source clauses, not chunks. A chunk covers a clause
when its merged source spans contain the whole anchor, so overlapping
chunks that repeat a clause count it once. A case with several acceptable
evidence sets is scored against the set it covers best:

    recall(case, chunks) = max over sets S of |covered(chunks) ∩ S| / |S|

Abstention cases have no evidence set; their recall is N/A and they are
scored by status.

A case passes when the status is the expected one, every required fact
matches the answer, and no prohibited fact does. Required facts count only
for an answered response. Prohibited facts are checked against whatever
answer text the user would see.
"""

from __future__ import annotations

import math
from statistics import mean

from app.evaluation.cases import Case, Clause


def merged_spans(spans: list[list[int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted((int(s), int(e)) for s, e in spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def covered_clauses(chunks: list[dict], clauses: dict[str, Clause]) -> set[str]:
    covered = set()
    for chunk in chunks:
        spans = merged_spans(chunk["source_spans"])
        for clause in clauses.values():
            if clause.document_version_id != chunk["document_version_id"]:
                continue
            if any(s <= clause.start and clause.end <= e for s, e in spans):
                covered.add(clause.clause_id)
    return covered


def set_recall(covered: set[str], evidence_sets: tuple[tuple[str, ...], ...]) -> dict | None:
    if not evidence_sets:
        return None
    scored = []
    for evidence in evidence_sets:
        hit = [c for c in evidence if c in covered]
        scored.append((len(hit) / len(evidence), len(evidence), list(evidence), [c for c in evidence if c not in covered]))
    best = max(scored, key=lambda s: (s[0], -s[1]))
    return {"recall": best[0], "best_set": best[2], "missing": best[3]}


def recall_report(case: Case, candidates: list[dict], ranked: list[dict], clauses: dict[str, Clause]) -> dict:
    def at(chunks):
        return set_recall(covered_clauses(chunks, clauses), case.evidence_sets)

    return {
        "candidate_recall_at_20": at(candidates[:20]),
        "recall_at_3": at(ranked[:3]),
        "recall_at_5": at(ranked[:5]),
    }


def answer_text(result: dict) -> str:
    return "" if result["status"] == "unavailable" else result["answer"]


def fact_report(case: Case, result: dict) -> dict:
    shown = answer_text(result)
    answered = result["status"] == "answered"
    required = {fact.fact_id: answered and fact.matches(shown) for fact in case.required}
    prohibited = {fact.fact_id: fact.matches(shown) for fact in case.prohibited}
    accuracy = (sum(required.values()) / len(required)) if required else None
    status_ok = result["status"] == case.expected_status
    passed = status_ok and all(required.values()) and not any(prohibited.values())
    return {
        "status": result["status"],
        "expected_status": case.expected_status,
        "status_ok": status_ok,
        "required": required,
        "prohibited": prohibited,
        "fact_accuracy": accuracy,
        "passed": passed,
    }


def citation_report(result: dict) -> dict:
    """Citation validity for a generated answer: no invented IDs and every citation resolves."""
    if result.get("generation") is None:
        return {"generated": False, "valid": None, "uncited": None}
    invented = result.get("invented_citation_ids", [])
    resolved = all(c["resolved"] for c in result["citations"])
    uncited = not result["citations"] and result["status"] != "insufficient_evidence"
    return {"generated": True, "valid": not invented and resolved, "invented": invented, "uncited": uncited}


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _avg(values: list) -> float | None:
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def summarize(outcomes: list[dict]) -> dict:
    """Macro averages over one group of per-case outcomes (one mode, one corpus kind)."""

    def recall(key):
        return _avg([o["recall"][key]["recall"] if o["recall"][key] else None for o in outcomes])

    answerable = [o for o in outcomes if o["expected_status"] == "answered"]
    generated = [o for o in outcomes if o.get("citations", {}).get("generated")]
    judged = [c for o in outcomes for c in (o.get("judge") or {}).get("claims", [])]
    latencies = [o["latency_ms"]["total"] for o in outcomes if o.get("latency_ms")]
    summary = {
        "cases": len(outcomes),
        "answerable_cases": len(answerable),
        "mean_eligible_chunks": _avg([o.get("eligible_chunks") for o in outcomes]),
        "candidate_recall_at_20": recall("candidate_recall_at_20"),
        "recall_at_3": recall("recall_at_3"),
        "recall_at_5": recall("recall_at_5"),
    }
    if any("facts" in o for o in outcomes):
        summary.update(
            {
                "fact_accuracy": _avg([o["facts"]["fact_accuracy"] for o in answerable if "facts" in o]),
                "case_pass_rate": _avg([1.0 if o["facts"]["passed"] else 0.0 for o in outcomes if "facts" in o]),
                "status_accuracy": _avg([1.0 if o["facts"]["status_ok"] else 0.0 for o in outcomes if "facts" in o]),
                "prohibited_fact_cases": sum(1 for o in outcomes if "facts" in o and any(o["facts"]["prohibited"].values())),
                "citation_validity": _avg([1.0 if o["citations"]["valid"] else 0.0 for o in generated]),
                "generated_answers": len(generated),
                "uncited_answers": sum(1 for o in generated if o["citations"]["uncited"]),
            }
        )
    if judged:
        summary["judge_support_score"] = _avg([1.0 if c["verdict"] == "supported" else 0.0 for c in judged])
        summary["judged_claims"] = len(judged)
    if latencies:
        summary["latency_ms"] = {"runs": len(latencies), "p50": percentile(latencies, 50), "p95": percentile(latencies, 95)}
    return summary
