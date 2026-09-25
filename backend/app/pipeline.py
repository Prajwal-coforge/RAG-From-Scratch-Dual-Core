"""One question through triage, retrieval, the applicability check, and answering."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from app.answer import answer_question
from app.retrieve import FINAL_K, retrieve
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
) -> dict:
    """snapshot_id and mode override triage's choice; triage still checks the question against the selected context."""
    started = time.perf_counter()
    selected = load_snapshot(snapshot_id).corpus_id if snapshot_id else None
    decision = triage(question, selected)
    decision["timing_ms"] = round((time.perf_counter() - started) * 1000, 1)
    if decision["status"] == "needs_clarification":
        return {"triage": decision, "retrieval": None,
                "answer": clarification(question, decision["reason"], decision["follow_up_questions"])}
    mode = mode or decision["mode"]
    retrieval = retrieve(
        session, index, embedder, question, snapshot_id or decision["snapshot_id"],
        k=k, as_of=as_of, include_history=include_history, mode=mode, reranker=reranker_for(mode),
    )
    top = retrieval["hits"][0] if retrieval["hits"] else None
    missing = missing_facts(retrieval["corpus_id"], question, top)
    if missing:
        section = f"{top['document_title']} / {top['heading_path']}"
        reason = f"the rule in {section} depends on {', '.join(m['fact'] for m in missing)}, which the question does not state"
        answer = clarification(question, reason, [m["follow_up"] for m in missing], retrieval=retrieval, missing_facts=missing)
    else:
        answer = answer_question(retrieval, embedder.tokenizer, chat_fn=chat_fn)
    return {"triage": decision, "retrieval": retrieval, "answer": answer}
