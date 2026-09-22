from __future__ import annotations

from policy_rag.config import CROSS_ENCODER_MODEL, RERANK_K
from policy_rag.retrieve import Hit

_model = None
_load_failed = False


def _cross_encoder():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(CROSS_ENCODER_MODEL)
    except Exception:
        _load_failed = True
        _model = None
    return _model


def rerank(question: str, hits: list[Hit], top_k: int = RERANK_K) -> list[Hit]:
    if not hits:
        return []
    model = _cross_encoder()
    if model is None:
        return hits[:top_k]
    pairs = [(question, hit.text) for hit in hits]
    scores = model.predict(pairs)
    ranked = sorted(
        zip(hits, scores, strict=True),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    out: list[Hit] = []
    for hit, score in ranked[:top_k]:
        hit.score = float(score)
        hit.source = f"{hit.source}+rerank"
        out.append(hit)
    return out
