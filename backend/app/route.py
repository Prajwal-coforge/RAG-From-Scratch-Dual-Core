"""Choose published policy contexts with the local chat model.

Used only when deterministic triage cannot name a single issuer. The model
picks corpus ids from the catalog; it does not answer the question. An
unusable reply searches every published context instead of asking the user
to pick one. The damaged dirty-stale snapshot is not in the catalog.
"""

from __future__ import annotations

import json

from app.answer import chat
from app.doctor import load_lock
from app.triage import contexts

ROUTER_FORMAT = {
    "type": "object",
    "properties": {"corpus_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["corpus_ids"],
}


def catalog_lines(ctxs) -> str:
    lines = []
    for ctx in ctxs:
        titles = "; ".join(f"{pid} {title}" for pid, title in sorted(ctx["policies"].items()))
        lines.append(f"- {ctx['corpus_id']}: {ctx['issuer']}. Policies: {titles}")
    return "\n".join(lines)


def parse_route(content: str, allowed: set[str]) -> list[str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    raw = data.get("corpus_ids") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    chosen = []
    for item in raw:
        if isinstance(item, str) and item in allowed and item not in chosen:
            chosen.append(item)
    return chosen


def route_corpora(question: str, chat_fn=None) -> dict:
    ctxs = list(contexts())
    by_id = {ctx["corpus_id"]: ctx for ctx in ctxs}
    system = (
        "You choose which policy corpora to search. You do not answer the question.\n"
        "Choose every corpus whose policies could state the rule. "
        "Choose one corpus when the question is about one issuer, or about a rule that only one corpus contains.\n"
        "Use only corpus ids from the catalog.\n\n"
        f"Catalog:\n{catalog_lines(ctxs)}"
    )
    basis = "chosen by the local chat model"
    raw = ""
    chosen: list[str] = []
    try:
        if chat_fn is None:
            lock = load_lock()
            call = chat(
                [{"role": "system", "content": system}, {"role": "user", "content": question}],
                ollama=lock["ollama_url"].rstrip("/"),
                model=lock["chat"]["model"],
                expected_digest=lock["chat"]["blob_digest"],
                format=ROUTER_FORMAT,
            )
        else:
            call = chat_fn(
                [{"role": "system", "content": system}, {"role": "user", "content": question}],
                format=ROUTER_FORMAT,
            )
        raw = call["response"]["message"]["content"]
        chosen = parse_route(raw, set(by_id))
        if not chosen:
            basis = "the model returned no catalog id, so every published context was searched"
    except Exception as exc:
        basis = f"model routing failed ({type(exc).__name__}); every published context was searched"
        chosen = []
    if not chosen:
        chosen = [ctx["corpus_id"] for ctx in ctxs]
    return {
        "status": "routed",
        "route": "model",
        "basis": basis,
        "corpus_ids": chosen,
        "snapshot_ids": [by_id[cid]["snapshot_id"] for cid in chosen],
        "raw": raw,
    }
