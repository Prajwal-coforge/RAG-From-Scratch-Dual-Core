"""Run an evaluation suite across retrieval modes and write one report.

Every case runs in every requested mode against the published generation of
its snapshot, with the same generation prompt, model, and settings. Metrics
are reported per mode, separately for the generated and imported corpora.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.answer import CHAT_OPTIONS, EVIDENCE_BUDGET_TOKENS, answer_question
from app.doctor import load_lock
from app.embedder import embedder_from_lock
from app.evaluation.cases import check_freeze, load_cases, load_clauses
from app.evaluation.judge import judge_answer
from app.evaluation.metrics import citation_report, covered_clauses, fact_report, recall_report, summarize
from app.evaluation.needle import run_needle
from app.ingest import connect
from app.keyword import B, EXACT_BOOST, K1
from app.rerank import reranker_from_lock
from app.retrieve import (
    CANDIDATE_K,
    FINAL_K,
    GRAPH_HOPS,
    KEYWORD_K,
    MAX_GRAPH_CANDIDATES,
    MAX_RERANK_CANDIDATES,
    MODES,
    RERANKED,
    RRF_K,
    VECTOR_K,
    retrieve,
)
from app.sources import ROOT, load_snapshot

TARGETS = {"candidate_recall_at_20": 0.90, "recall_at_5": 0.85, "fact_accuracy": 0.85, "citation_validity": 1.0}


def git_commit() -> str:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return head + ("-dirty" if dirty else "")


def configuration(lock: dict, modes: list[str], answers: bool, judge: bool) -> dict:
    return {
        "modes": modes,
        "retrieval": {
            "candidate_k": CANDIDATE_K, "vector_k": VECTOR_K, "keyword_k": KEYWORD_K, "rrf_k": RRF_K,
            "final_k": FINAL_K, "max_rerank_candidates": MAX_RERANK_CANDIDATES,
            "graph": {"hops": GRAPH_HOPS, "max_added": MAX_GRAPH_CANDIDATES, "edge": "REFERENCES", "validation_status": "validated"},
            "bm25": {"k1": K1, "b": B, "exact_boost": EXACT_BOOST},
        },
        "embedder": lock["embedding"],
        "reranker": lock["reranker"],
        "generation": {"model": lock["chat"]["model"], "blob_digest": lock["chat"]["blob_digest"], "options": CHAT_OPTIONS,
                       "think": False, "evidence_budget_tokens": EVIDENCE_BUDGET_TOKENS} if answers else None,
        "judge": {"model": lock["chat"]["model"], "same_model_as_generator": True, "gating": False} if judge else None,
        "targets": TARGETS,
    }


def target_check(summary: dict) -> dict:
    checks = {}
    for metric, target in TARGETS.items():
        value = summary.get(metric)
        checks[metric] = {"value": value, "target": target, "met": None if value is None else value >= target}
    return checks


def evaluate(
    split: str,
    modes: list[str],
    *,
    answers: bool = True,
    judge: bool = True,
    needle: bool = True,
    case_ids: list[str] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        raise ValueError(f"unknown modes {unknown}; choose from {MODES}")
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lock = load_lock()
    clauses = load_clauses()
    freeze = check_freeze() if split == "heldout" else None
    cases = load_cases(split, clauses)
    if case_ids:
        cases = [c for c in cases if c.case_id in case_ids]
    embedder = embedder_from_lock(lock)
    reranker = reranker_from_lock(lock) if set(modes) & set(RERANKED) else None
    sources: dict[str, dict[str, str]] = {}
    outcomes = []
    first_answer = True
    driver, index = connect()
    try:
        with driver.session() as session:
            for case in cases:
                if case.snapshot_id not in sources:
                    sources[case.snapshot_id] = {d.document_version_id: d.text for d in load_snapshot(case.snapshot_id).documents}
                for mode in modes:
                    retrieval = retrieve(
                        session, index, embedder, case.question, case.snapshot_id,
                        as_of=case.as_of, include_history=case.include_history, mode=mode, reranker=reranker,
                    )
                    outcome = {
                        "case_id": case.case_id,
                        "mode": mode,
                        "corpus_kind": case.corpus_kind,
                        "corpus_id": case.corpus_id,
                        "snapshot_id": case.snapshot_id,
                        "index_generation_id": retrieval["index_generation_id"],
                        "as_of": retrieval["as_of"],
                        "question": case.question,
                        "expected_status": case.expected_status,
                        "eligible_chunks": retrieval["search"]["eligible"],
                        "recall": recall_report(case, retrieval["candidates"], retrieval["hits"], clauses),
                        "ranked": [
                            {
                                "rank": hit["rank"],
                                "chunk_id": hit["chunk_id"],
                                "where": f"{hit['document_title']} / {hit['heading_path']}",
                                "clauses": sorted(covered_clauses([hit], clauses)),
                                "signals": hit["signals"],
                            }
                            for hit in retrieval["hits"]
                        ],
                        "latency_ms": {"retrieval": retrieval["timing_ms"], "stages": retrieval["stage_timing_ms"]},
                    }
                    if answers:
                        result = answer_question(retrieval, embedder.tokenizer, sources=sources[case.snapshot_id])
                        outcome["answer"] = {
                            k: result.get(k)
                            for k in ("status", "answer", "validation_problems", "invented_citation_ids", "claims", "evidence_budget")
                        }
                        outcome["answer"]["citations"] = [
                            {k: c[k] for k in ("citation_id", "chunk_id", "document_title", "section_path", "source_spans", "resolved")}
                            for c in result["citations"]
                        ]
                        outcome["answer"]["evidence"] = [
                            {k: e.get(k) for k in ("evidence_id", "chunk_id", "role", "tokens")} for e in result["evidence"]
                        ] if "evidence" in result else []
                        outcome["facts"] = fact_report(case, result)
                        outcome["citations"] = citation_report(result)
                        outcome["latency_ms"]["answer"] = result["timing_ms"]
                        outcome["latency_ms"]["first_answer_of_run"] = first_answer and result.get("generation") is not None
                        if result.get("generation") is not None:
                            first_answer = False
                        if judge:
                            verdict = judge_answer(result)
                            outcome["judge"] = verdict
                            if verdict and verdict["all_supported"] is not None:
                                outcome["judge_disagrees"] = verdict["all_supported"] != outcome["facts"]["passed"]
                    outcome["latency_ms"]["total"] = round(
                        outcome["latency_ms"]["retrieval"] + outcome["latency_ms"].get("answer", 0.0), 1
                    )
                    outcomes.append(outcome)
                    log(line_for(outcome))
            needle_report = None
            if needle:
                log("needle check in an isolated index")
                needle_report = run_needle(session, lock, embedder, reranker, modes=modes)
                for row in needle_report["results"]:
                    log(f"  needle {row['query']:10} {row['mode']:13} rank {row['needle_rank']}")
                log(f"  isolation ok {needle_report['isolation']['ok']}")
    finally:
        driver.close()

    summary: dict = {}
    for mode in modes:
        in_mode = [o for o in outcomes if o["mode"] == mode]
        summary[mode] = {
            "all": summarize(in_mode),
            "generated": summarize([o for o in in_mode if o["corpus_kind"] == "generated"]),
            "imported": summarize([o for o in in_mode if o["corpus_kind"] == "imported"]),
        }
        summary[mode]["targets"] = target_check(summary[mode]["all"])
    return {
        "suite": split,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git_commit(),
        "configuration": configuration(lock, modes, answers, judge),
        "freeze": freeze,
        "case_count": len(cases),
        "recall_formula": "max over acceptable evidence sets S of |covered clauses in S| / |S|; abstention cases N/A",
        "recall_caveat": (
            "Candidate recall@20 is computed over the eligible chunks of one snapshot. When the eligible pool is "
            "not much larger than 20, it is close to 1 by construction; see mean_eligible_chunks."
        ),
        "summary": summary,
        "judge_disagreements": [
            {"case_id": o["case_id"], "mode": o["mode"], "deterministic_pass": o["facts"]["passed"], "judge_all_supported": o["judge"]["all_supported"]}
            for o in outcomes
            if o.get("judge_disagrees")
        ],
        "needle": needle_report,
        "outcomes": outcomes,
    }


def line_for(outcome: dict) -> str:
    recall = outcome["recall"]

    def fmt(key):
        value = recall[key]
        return "n/a " if value is None else f"{value['recall']:.2f}"

    text = (
        f"{outcome['case_id']:6} {outcome['mode']:13} cand@20 {fmt('candidate_recall_at_20')} "
        f"r@3 {fmt('recall_at_3')} r@5 {fmt('recall_at_5')}"
    )
    if "facts" in outcome:
        facts = outcome["facts"]
        accuracy = "n/a " if facts["fact_accuracy"] is None else f"{facts['fact_accuracy']:.2f}"
        text += f"  {facts['status']:21} facts {accuracy} {'PASS' if facts['passed'] else 'FAIL'}"
    if outcome.get("judge"):
        text += f"  judge {outcome['judge']['all_supported']}"
    return text + f"  {outcome['latency_ms']['total']:.0f} ms"


def print_summary(report: dict) -> None:
    keys = ("candidate_recall_at_20", "recall_at_3", "recall_at_5", "fact_accuracy", "case_pass_rate",
            "citation_validity", "judge_support_score")
    for mode, groups in report["summary"].items():
        print(f"{mode}:")
        for group in ("all", "generated", "imported"):
            s = groups[group]
            values = "  ".join(f"{k} {s[k]:.2f}" if s.get(k) is not None else f"{k} n/a" for k in keys)
            latency = s.get("latency_ms") or {}
            print(f"  {group:9} cases {s['cases']:2}  {values}  p50 {latency.get('p50')} p95 {latency.get('p95')} ms")
        unmet = [k for k, v in groups["targets"].items() if v["met"] is False]
        unmeasured = [k for k, v in groups["targets"].items() if v["met"] is None]
        print(
            f"  targets: {'not met: ' + ', '.join(unmet) if unmet else 'all measured targets met'}"
            f"{'; not measured: ' + ', '.join(unmeasured) if unmeasured else ''}"
            f"  (mean eligible pool {groups['all']['mean_eligible_chunks']:.1f} chunks)"
        )
    for row in report["judge_disagreements"]:
        print(f"judge disagrees: {row}")
    if report["needle"]:
        print(f"needle isolation ok: {report['needle']['isolation']['ok']}")
    if report["freeze"]:
        freeze = report["freeze"]
        print(f"held-out freeze {freeze['frozen_at']}: hashes match; labels {freeze.get('review_status', 'review status not recorded')}")


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
