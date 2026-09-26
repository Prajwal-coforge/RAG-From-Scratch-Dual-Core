"""One question through triage, retrieval, the applicability check, and answering."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from app.answer import answer_question
from app.retrieve import FINAL_K, retrieve
from app.route import route_corpora
from app.sources import load_snapshot
from app.triage import missing_facts, triage


def clarification(question: str, reason: str, follow_ups: list[str], *, retrieval: dict | None = None, **extra) -> dict:
    return {
        "request_id": f"req-{uuid.uuid4().hex[:12]}",
        "trace_id": f"trace-{uuid.uuid4().hex[:12]}",
        "status": "needs_clarification",
        "question": question,
        "answer": f"More information is needed: {reason}.",
        "follow_up_questions": follow_ups,
        "claims": [],
        "citations": [],
        "generation": None,
        "mode_used": retrieval["mode"] if retrieval else None,
        "corpus_id": retrieval["corpus_id"] if retrieval else None,
        "snapshot_id": retrieval["snapshot_id"] if retrieval else None,
        "index_generation_id": retrieval["index_generation_id"] if retrieval else None,
        "timing_ms": 0.0,
        **extra,
    }


def resolve_context(question: str, snapshot_id: str | None, router_fn: Callable[[str], dict]) -> dict:
    """Pick the published contexts to search.

    An explicit snapshot stays in force, and triage still rejects a question
    that names a different issuer. With no snapshot, a named issuer or a
    dominant vocabulary match is used directly. Otherwise the local model
    chooses one or more catalog contexts. The user is not asked to pick.
    """
    if snapshot_id is not None:
        return triage(question, load_snapshot(snapshot_id).corpus_id)
    decision = triage(question)
    if decision["status"] == "routed":
        return decision
    routed = router_fn(question)
    if len(routed["snapshot_ids"]) == 1:
        corpus_id = routed["corpus_ids"][0]
        inner = triage(question, corpus_id)
        mode = inner["mode"] if inner["status"] == "routed" else "hybrid_rerank"
        route = inner["route"] if inner["status"] == "routed" else "model"
        return {
            **routed,
            "status": "routed",
            "route": route,
            "mode": mode,
            "corpus_id": corpus_id,
            "snapshot_id": routed["snapshot_ids"][0],
        }
    return {**routed, "mode": "hybrid_rerank"}


def _hit_score(hit: dict) -> float:
    signals = hit.get("signals") or {}
    if signals.get("rerank_score") is not None:
        return float(signals["rerank_score"])
    if hit.get("similarity") is not None:
        return float(hit["similarity"])
    return float(signals.get("rrf") or 0.0)


def merge_retrievals(question: str, results: list[dict], k: int) -> dict:
    """Order passages from several contexts by the same rerank score."""
    ranked = sorted(
        ((_hit_score(hit), result, hit) for result in results for hit in result["hits"]),
        key=lambda row: row[0],
        reverse=True,
    )
    hits = []
    seen = set()
    context = {}
    for _score, result, hit in ranked:
        if hit["chunk_id"] in seen:
            continue
        seen.add(hit["chunk_id"])
        hits.append({**hit, "rank": len(hits) + 1})
        for cid, chunk in result.get("context_chunks", {}).items():
            context.setdefault(cid, chunk)
        if len(hits) == k:
            break
    modes = list(dict.fromkeys(result["mode"] for result in results))
    return {
        "mode": modes[0] if len(modes) == 1 else "hybrid_rerank",
        "question": question,
        "k": k,
        "query_input": results[0].get("query_input"),
        "snapshot_id": results[0]["snapshot_id"],
        "snapshot_ids": [result["snapshot_id"] for result in results],
        "corpus_id": results[0]["corpus_id"] if len(results) == 1 else "multiple",
        "corpus_ids": [result["corpus_id"] for result in results],
        "index_generation_id": ", ".join(result["index_generation_id"] for result in results),
        "as_of": results[0]["as_of"],
        "include_history": results[0]["include_history"],
        "embedder": results[0].get("embedder"),
        "timing_ms": round(sum(result["timing_ms"] for result in results), 1),
        "stage_timing_ms": {result["snapshot_id"]: result["stage_timing_ms"] for result in results},
        "search": {
            "method": "each chosen context was searched, then passages were ordered by cross-encoder score",
            "eligible": sum(result["search"]["eligible"] for result in results),
            "generation_chunks": sum(result["search"]["generation_chunks"] for result in results),
            "excluded": [row for result in results for row in result["search"]["excluded"]],
            "stages": {"contexts": [
                {"snapshot_id": result["snapshot_id"], "corpus_id": result["corpus_id"], "mode": result["mode"]}
                for result in results
            ]},
        },
        "hits": hits,
        "context_chunks": context,
        "candidates": [row for result in results for row in result.get("candidates", [])],
    }


def ask_question(
    session,
    index: str,
    embedder,
    question: str,
    *,
    reranker_for: Callable[[str], object],
    snapshot_id: str | None = None,
    mode: str | None = None,
    k: int = FINAL_K,
    as_of: str | None = None,
    include_history: bool = False,
    chat_fn=None,
    router_fn: Callable[[str], dict] | None = None,
) -> dict:
    """An explicit snapshot overrides routing. With none, the model chooses contexts when triage cannot."""
    started = time.perf_counter()
    decision = resolve_context(question, snapshot_id, router_fn or route_corpora)
    decision["timing_ms"] = round((time.perf_counter() - started) * 1000, 1)
    if decision["status"] == "needs_clarification":
        return {"triage": decision, "retrieval": None,
                "answer": clarification(question, decision["reason"], decision["follow_up_questions"])}
    snapshot_ids = decision.get("snapshot_ids") or [snapshot_id or decision["snapshot_id"]]
    results = []
    for one in snapshot_ids:
        corpus_id = load_snapshot(one).corpus_id
        inner = triage(question, corpus_id)
        one_mode = mode or (inner["mode"] if inner["status"] == "routed" else decision.get("mode") or "hybrid_rerank")
        results.append(retrieve(
            session, index, embedder, question, one,
            k=k, as_of=as_of, include_history=include_history, mode=one_mode, reranker=reranker_for(one_mode),
        ))
    retrieval = results[0] if len(results) == 1 else merge_retrievals(question, results, k)
    if len(results) == 1:
        retrieval = {**retrieval, "snapshot_ids": snapshot_ids}
    top = retrieval["hits"][0] if retrieval["hits"] else None
    missing = missing_facts(results[0]["corpus_id"], question, top) if len(results) == 1 else []
    if missing:
        section = f"{top['document_title']} / {top['heading_path']}"
        reason = f"the rule in {section} depends on {', '.join(m['fact'] for m in missing)}, which the question does not state"
        answer = clarification(question, reason, [m["follow_up"] for m in missing], retrieval=retrieval, missing_facts=missing)
    else:
        answer = answer_question(retrieval, embedder.tokenizer, chat_fn=chat_fn)
    return {"triage": decision, "retrieval": retrieval, "answer": answer}
