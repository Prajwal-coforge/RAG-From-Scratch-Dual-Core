"""Vector retrieval over the published generation of one snapshot.

Search goes through the Memgraph vector index. Because the index is shared by
every generation, k is the whole index size and results are then filtered to
the published generation, so no eligible chunk is cut off by other
generations' neighbours. The stored vectors are also scored with exact
cosine in Python as a check; both scores are reported.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import date

from app.embeddings import cosine, format_query

SCORE_AGREEMENT = 1e-4


class RetrievalRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class Hit:
    rank: int
    chunk_id: str
    document_version_id: str
    document_title: str
    corpus_id: str
    policy_id: str
    version: str
    publication_status: str | None
    effective_from: str | None
    effective_to: str | None
    section_id: str
    heading_path: str
    text: str
    source_spans: list[list[int]]
    similarity: float
    exact_cosine: float

    def as_dict(self) -> dict:
        return asdict(self)


HISTORY_STATUSES = ("active", "superseded")


def eligibility(props: dict, as_of: str, include_history: bool) -> str | None:
    """Return why a chunk is excluded, or None when it may be used.

    Ordinary questions use versions that are active now and in force on
    as_of. History questions use whichever active or superseded version was
    in force on as_of, because a superseded version was once the rule.
    """
    status = props.get("publication_status")
    allowed = HISTORY_STATUSES if include_history else ("active",)
    if status not in allowed:
        return f"status {status}"
    day = date.fromisoformat(as_of)
    start, end = props.get("effective_from"), props.get("effective_to")
    if start and date.fromisoformat(start) > day:
        return f"not yet effective ({start})"
    if end and date.fromisoformat(end) < day:
        return f"expired ({end})"
    return None


def published_generation(session, snapshot_id: str) -> dict:
    row = session.run(
        "MATCH (p:Publication {snapshot_id: $s}) MATCH (g:IndexGeneration {id: p.current}) RETURN properties(g) AS g",
        s=snapshot_id,
    ).single()
    if row is None:
        raise RetrievalRefused(f"snapshot {snapshot_id!r} has no published generation; run ingest --snapshot {snapshot_id}")
    generation = dict(row["g"])
    if generation.get("status") != "published":
        raise RetrievalRefused(f"generation {generation['id']} is {generation.get('status')}, not published")
    return generation


def check_compatible(generation: dict, embedder) -> None:
    built_with = json.loads(generation["embedder"])
    if built_with != embedder.identity:
        raise RetrievalRefused(
            f"generation {generation['id']} was built with {built_with}; the query embedder is {embedder.identity}. "
            "Re-ingest with the current embedder or select a compatible generation."
        )


def retrieve(
    session,
    index: str,
    embedder,
    question: str,
    snapshot_id: str,
    *,
    k: int = 5,
    as_of: str | None = None,
    include_history: bool = False,
) -> dict:
    started = time.perf_counter()
    generation = published_generation(session, snapshot_id)
    check_compatible(generation, embedder)
    as_of = as_of or generation["as_of"]
    date.fromisoformat(as_of)
    query_input = format_query(question)
    query_vector = embedder.embed([query_input])[0]

    info = session.run("CALL vector_search.show_index_info() YIELD * RETURN *").data()
    size = next(int(row["size"]) for row in info if row["index_name"] == index)
    rows = session.run(
        "CALL vector_search.search($index, $k, $v) YIELD node, similarity "
        "WHERE node.generation_id = $g "
        "RETURN properties(node) AS props, similarity ORDER BY similarity DESC",
        index=index,
        k=size,
        v=query_vector,
        g=generation["id"],
    ).data()
    if len(rows) != generation["chunk_count"]:
        raise RetrievalRefused(
            f"vector index returned {len(rows)} of {generation['chunk_count']} chunks for {generation['id']}"
        )

    eligible, excluded = [], []
    for row in rows:
        props = row["props"]
        reason = eligibility(props, as_of, include_history)
        exact = cosine(query_vector, props["embedding"])
        if reason:
            excluded.append({"chunk_id": props["chunk_id"], "document_version_id": props["document_version_id"], "reason": reason})
            continue
        eligible.append((props, float(row["similarity"]), exact))

    by_index = [p["chunk_id"] for p, _s, _e in eligible]
    by_exact = [p["chunk_id"] for p, _s, _e in sorted(eligible, key=lambda item: item[2], reverse=True)]
    max_score_gap = max((abs(s - e) for _p, s, e in eligible), default=0.0)
    hits = [
        Hit(
            rank=rank,
            chunk_id=props["chunk_id"],
            document_version_id=props["document_version_id"],
            document_title=props["document_title"],
            corpus_id=props["corpus_id"],
            policy_id=props["policy_id"],
            version=props["version"],
            publication_status=props.get("publication_status"),
            effective_from=props.get("effective_from"),
            effective_to=props.get("effective_to"),
            section_id=props["section_id"],
            heading_path=props["heading_path"],
            text=props["text"],
            source_spans=json.loads(props["source_spans"]),
            similarity=similarity,
            exact_cosine=exact,
        )
        for rank, (props, similarity, exact) in enumerate(eligible[:k], start=1)
    ]
    return {
        "mode": "vector",
        "snapshot_id": snapshot_id,
        "corpus_id": generation["corpus_id"],
        "index_generation_id": generation["id"],
        "as_of": as_of,
        "include_history": include_history,
        "question": question,
        "query_input": query_input,
        "embedder": embedder.identity,
        "k": k,
        "search": {
            "method": f"Memgraph vector_search.search on {index}, k = index size {size}, filtered to the generation",
            "generation_chunks": len(rows),
            "eligible": len(eligible),
            "excluded": excluded,
        },
        "exact_check": {
            "top_k_agrees": by_index[:k] == by_exact[:k],
            "max_score_gap": max_score_gap,
            "scores_agree": max_score_gap <= SCORE_AGREEMENT,
        },
        "hits": [hit.as_dict() for hit in hits],
        "timing_ms": round((time.perf_counter() - started) * 1000, 1),
    }
