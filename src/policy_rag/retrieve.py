from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from policy_rag.config import KEYWORD_K, RRF_K, VECTOR_K


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict[str, str]
    score: float
    source: str


def vector_hits(
    collection: Any,
    query_embedding: list[float],
    k: int = VECTOR_K,
) -> list[Hit]:
    from policy_rag.store import query_vector

    raw = query_vector(collection, query_embedding, n_results=max(k, 1))
    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]
    hits: list[Hit] = []
    for i, doc_id in enumerate(ids):
        dist = dists[i] if i < len(dists) else 1.0
        hits.append(
            Hit(
                id=doc_id,
                text=docs[i] if i < len(docs) else "",
                metadata=dict(metas[i] or {}) if i < len(metas) else {},
                score=1.0 / (1.0 + float(dist)),
                source="vector",
            )
        )
    return hits


def keyword_hits(
    collection: Any,
    question: str,
    k: int = KEYWORD_K,
) -> list[Hit]:
    from policy_rag.store import all_records

    needle = question.strip().lower()
    if not needle:
        return []
    records = all_records(collection)
    scored: list[Hit] = []
    for i, text in enumerate(records.get("documents") or []):
        blob = text or ""
        hay = blob.lower()
        if needle not in hay and not _token_hit(needle, hay):
            continue
        meta = (records.get("metadatas") or [])[i] or {}
        section = str(meta.get("section", "")).lower()
        boost = 2.0 if any(tok in section for tok in needle.split() if len(tok) > 2) else 1.0
        scored.append(
            Hit(
                id=(records.get("ids") or [])[i],
                text=blob,
                metadata=dict(meta),
                score=boost + hay.count(needle),
                source="keyword",
            )
        )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:k]


def _token_hit(needle: str, hay: str) -> bool:
    tokens = [t for t in re_tokens(needle) if len(t) > 2]
    return any(tok in hay for tok in tokens)


def re_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9.]+", text.lower())


def rrf_merge(rankings: list[list[Hit]], k: int = RRF_K) -> list[Hit]:
    by_id: dict[str, Hit] = {}
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.id] += 1.0 / (k + rank)
            prev = by_id.get(hit.id)
            if prev is None:
                by_id[hit.id] = hit
            else:
                sources = {prev.source, hit.source}
                prev.source = "+".join(sorted(sources))
                prev.score = max(prev.score, hit.score)
    ordered = sorted(by_id.values(), key=lambda h: scores[h.id], reverse=True)
    for hit in ordered:
        hit.score = scores[hit.id]
    return ordered


def hybrid_retrieve(
    collection: Any,
    question: str,
    query_embedding: list[float],
    vector_k: int = VECTOR_K,
    keyword_k: int = KEYWORD_K,
) -> list[Hit]:
    return rrf_merge(
        [
            vector_hits(collection, query_embedding, k=vector_k),
            keyword_hits(collection, question, k=keyword_k),
        ]
    )
