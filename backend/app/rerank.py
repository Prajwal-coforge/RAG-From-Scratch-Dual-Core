"""Cross-encoder reranking with checked 512-token question-passage pairs.

The passage is "<document title> <heading> <chunk text>". The reranker's
WordPiece tokenizer ignores whitespace, so the pair's token count is the
question, the prefix, the text, and three special tokens. A pair over the
limit is split into windows with the chunker's rerank splitter, each window
is checked again, and the chunk takes its best window score. Nothing is
truncated.

Scores are the model's raw relevance logits. They order passages; they are
not probabilities of being correct.
"""

from __future__ import annotations

from functools import lru_cache
from types import SimpleNamespace

from app.chunking.chunk import ChunkConfig, split_rerank_windows

BATCH_SIZE = 16


class RerankOverflow(ValueError):
    pass


class PairTokenizer:
    def __init__(self, tokenizer, revision: str):
        self._tokenizer = tokenizer
        self.name = f"ms-marco-minilm-{revision[:12]}"

    def count(self, text: str) -> int:
        if not text or not text.strip():
            return 0
        return len(self._tokenizer(text, add_special_tokens=False)["input_ids"])

    def pair(self, question: str, passage: str) -> int:
        return len(self._tokenizer(question, passage, truncation=False)["input_ids"])


class Reranker:
    def __init__(self, model_id: str, revision: str, max_pair_tokens: int, *, model=None):
        if model is None:
            model = _load_pinned(model_id, revision, max_pair_tokens)
        self.model_id = model_id
        self.revision = revision
        self.max_pair_tokens = max_pair_tokens
        self._model = model
        self.tokenizer = PairTokenizer(model.tokenizer, revision)
        self.config = ChunkConfig(rerank_pair_tokens=max_pair_tokens)

    @property
    def identity(self) -> dict:
        return {"model": self.model_id, "revision": self.revision, "max_pair_tokens": self.max_pair_tokens}

    @staticmethod
    def prefix(candidate: dict) -> str:
        return f"{candidate['document_title']} {candidate['heading_path']}"

    def pairs_for(self, question: str, candidate: dict) -> list[tuple[str, str]]:
        passage = f"{self.prefix(candidate)} {candidate['text']}"
        if self.tokenizer.pair(question, passage) <= self.max_pair_tokens:
            return [(question, passage)]
        chunk = SimpleNamespace(
            chunk_id=candidate["chunk_id"],
            document_title=candidate["document_title"],
            heading_path=candidate["heading_path"],
            text=candidate["text"],
            spans=tuple(tuple(span) for span in candidate["source_spans"]),
        )
        pairs = []
        for window in split_rerank_windows(chunk, question, self.tokenizer, self.config):
            passage = f"{self.prefix(candidate)} {window.text}"
            if self.tokenizer.pair(question, passage) > self.max_pair_tokens:
                raise RerankOverflow(f"window of {candidate['chunk_id']} still exceeds {self.max_pair_tokens} tokens")
            pairs.append((question, passage))
        return pairs

    def score(self, question: str, candidates: list[dict]) -> list[dict]:
        """Return one record per candidate, highest score first, with the ranks before and after."""
        groups = [self.pairs_for(question, candidate) for candidate in candidates]
        flat = [pair for group in groups for pair in group]
        scores = [float(s) for s in self._model.predict(flat, batch_size=BATCH_SIZE, show_progress_bar=False)] if flat else []
        records, cursor = [], 0
        for before, (candidate, group) in enumerate(zip(candidates, groups), start=1):
            window_scores = scores[cursor : cursor + len(group)]
            cursor += len(group)
            records.append(
                {
                    "chunk_id": candidate["chunk_id"],
                    "rerank_score": max(window_scores),
                    "windows": len(group),
                    "pair_tokens": max(self.tokenizer.pair(q, p) for q, p in group),
                    "rank_before": before,
                }
            )
        records.sort(key=lambda r: (-r["rerank_score"], r["rank_before"]))
        for after, record in enumerate(records, start=1):
            record["rank_after"] = after
        return records


def _load_pinned(model_id: str, revision: str, max_length: int):
    from sentence_transformers import CrossEncoder

    try:
        return CrossEncoder(model_id, revision=revision, max_length=max_length, local_files_only=True)
    except OSError:
        return CrossEncoder(model_id, revision=revision, max_length=max_length)


@lru_cache(maxsize=1)
def load_reranker(model_id: str, revision: str, max_pair_tokens: int) -> Reranker:
    return Reranker(model_id, revision, max_pair_tokens)


def reranker_from_lock(lock: dict) -> Reranker:
    spec = lock["reranker"]
    return load_reranker(spec["model"], spec["revision"], spec["maximum_pair_tokens"])
