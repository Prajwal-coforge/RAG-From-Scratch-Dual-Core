"""Retrieval over the published generation of one snapshot, in five modes.

vector         Memgraph vector search, top 20 candidates
keyword        BM25 with an exact-identifier boost, top 20 candidates
hybrid         reciprocal rank fusion of vector top 10 and keyword top 10
hybrid_rerank  the hybrid candidates reordered by a cross-encoder
graph_rerank   the hybrid candidates plus chunks reached over one validated
               REFERENCES edge, reordered by the cross-encoder. A reference
               naming a section adds that section's chunks; a reference to a
               whole policy adds its two chunks most similar to the question.
               At most ten chunks are added, each with its path.

Each mode returns its candidate pool (the chunks the final stage chooses
from, used for candidate recall) and the final top k, with every signal
that produced the order.

Vector search goes through the Memgraph vector index. Because the index is
shared by every generation, k is the whole index size and results are then
filtered to the generation, so no eligible chunk is cut off by other
generations' neighbours. The stored vectors are also scored with exact
cosine in Python as a check; both scores are reported.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from app.embeddings import cosine, format_query
from app.graph import section_number
from app.keyword import BM25Index

SCORE_AGREEMENT = 1e-4
MODES = ("vector", "keyword", "hybrid", "hybrid_rerank", "graph_rerank")
RERANKED = ("hybrid_rerank", "graph_rerank")
CANDIDATE_K = 20
VECTOR_K = 10
KEYWORD_K = 10
RRF_K = 60
FINAL_K = 5
MAX_RERANK_CANDIDATES = 30
GRAPH_HOPS = 1
MAX_GRAPH_CANDIDATES = 10
POLICY_REFERENCE_CHUNKS = 2
LABEL = "Chunk"


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
    similarity: float | None
    exact_cosine: float | None
    signals: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


HISTORY_STATUSES = ("active", "superseded")


def latest_in_force_date(rows: list[dict], today: date | None = None) -> str:
    """The day the newest active version is already in force.

    Active chunks contribute their effective_from. The result is the latest
    of those dates, and not a date after today, so a future version is not
    treated as current. Chunks with no effective date do not move the result.
    If none record a date, the result is today.
    """
    today = today or date.today()
    starts = []
    for row in rows:
        if row.get("publication_status") != "active":
            continue
        start = row.get("effective_from")
        if not start:
            continue
        starts.append(date.fromisoformat(start))
    if not starts:
        return today.isoformat()
    return min(max(starts), today).isoformat()


def resolve_as_of(session, generation: dict, as_of: str | None, label: str = LABEL) -> tuple[str, str]:
    """A caller-supplied date is kept. Otherwise the newest active version decides."""
    if not label.isidentifier():
        raise ValueError(f"bad label {label!r}")
    if as_of:
        date.fromisoformat(as_of)
        return as_of, "caller"
    rows = session.run(
        f"MATCH (c:{label} {{generation_id: $g}}) "
        "RETURN c.publication_status AS publication_status, c.effective_from AS effective_from",
        g=generation["id"],
    ).data()
    return latest_in_force_date(rows), "latest active effective date"


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


@dataclass
class Pool:
    """Every chunk of one generation, split into eligible and excluded."""

    generation: dict
    chunks: dict[str, dict]
    eligible: list[str]
    excluded: list[dict]
    label: str = LABEL
    references: dict[str, list[dict]] = field(default_factory=dict)

    @property
    def eligible_chunks(self) -> list[dict]:
        return [self.chunks[cid] for cid in self.eligible]


def load_pool(session, generation: dict, as_of: str, include_history: bool, label: str = LABEL) -> Pool:
    if not label.isidentifier():
        raise ValueError(f"bad label {label!r}")
    rows = session.run(f"MATCH (c:{label} {{generation_id: $g}}) RETURN properties(c) AS props", g=generation["id"]).data()
    chunks, eligible, excluded = {}, [], []
    for row in sorted(rows, key=lambda r: r["props"]["chunk_id"]):
        props = dict(row["props"])
        props["source_spans"] = json.loads(props["source_spans"])
        chunks[props["chunk_id"]] = props
        reason = eligibility(props, as_of, include_history)
        if reason:
            excluded.append({"chunk_id": props["chunk_id"], "document_version_id": props["document_version_id"], "reason": reason})
        else:
            eligible.append(props["chunk_id"])
    if len(chunks) != generation["chunk_count"]:
        raise RetrievalRefused(f"generation {generation['id']} has {len(chunks)} of {generation['chunk_count']} chunks")
    references: dict[str, list[dict]] = {}
    if label == LABEL:
        rows = session.run(
            "MATCH (s:Section {generation_id: $g})-[r:REFERENCES]->(p:Policy) WHERE r.validation_status = 'validated' "
            "RETURN s.section_id AS section_id, p.policy_id AS target, p.corpus_id AS corpus_id, r.target_section AS target_section, "
            "r.evidence AS evidence, r.source_start AS start, r.source_end AS end, r.document_version_id AS document_version_id "
            "ORDER BY section_id, target, target_section",
            g=generation["id"],
        ).data()
        for row in rows:
            references.setdefault(row["section_id"], []).append(row)
    return Pool(generation, chunks, eligible, excluded, label, references)


def vector_ranking(session, index: str, pool: Pool, query_vector: list[float]) -> tuple[list[dict], dict]:
    """Rank every eligible chunk by index similarity, with exact cosine alongside."""
    info = session.run("CALL vector_search.show_index_info() YIELD * RETURN *").data()
    size = next(int(row["size"]) for row in info if row["index_name"] == index)
    rows = session.run(
        "CALL vector_search.search($index, $k, $v) YIELD node, similarity "
        "WHERE node.generation_id = $g "
        "RETURN node.chunk_id AS chunk_id, similarity ORDER BY similarity DESC",
        index=index,
        k=size,
        v=query_vector,
        g=pool.generation["id"],
    ).data()
    if len(rows) != pool.generation["chunk_count"]:
        raise RetrievalRefused(
            f"vector index returned {len(rows)} of {pool.generation['chunk_count']} chunks for {pool.generation['id']}"
        )
    eligible = set(pool.eligible)
    ranking = [
        {
            "chunk_id": row["chunk_id"],
            "similarity": float(row["similarity"]),
            "exact_cosine": cosine(query_vector, pool.chunks[row["chunk_id"]]["embedding"]),
        }
        for row in rows
        if row["chunk_id"] in eligible
    ]
    for rank, item in enumerate(ranking, start=1):
        item["rank"] = rank
    search = {"method": f"Memgraph vector_search.search on {index}, k = index size {size}, filtered to the generation"}
    return ranking, search


def exact_check(ranking: list[dict], k: int) -> dict:
    by_index = [r["chunk_id"] for r in ranking]
    by_exact = [r["chunk_id"] for r in sorted(ranking, key=lambda r: r["exact_cosine"], reverse=True)]
    gap = max((abs(r["similarity"] - r["exact_cosine"]) for r in ranking), default=0.0)
    return {"top_k_agrees": by_index[:k] == by_exact[:k], "max_score_gap": gap, "scores_agree": gap <= SCORE_AGREEMENT}


def rrf_fuse(vector: list[dict], keyword: list[dict], k: int = RRF_K) -> list[dict]:
    """Reciprocal rank fusion: score = sum of 1 / (k + rank) over the lists a chunk appears in."""
    fused: dict[str, dict] = {}
    for signal, results in (("vector", vector), ("keyword", keyword)):
        for result in results:
            entry = fused.setdefault(result["chunk_id"], {"chunk_id": result["chunk_id"], "rrf": 0.0, "rrf_parts": {}})
            part = 1.0 / (k + result["rank"])
            entry["rrf_parts"][signal] = part
            entry["rrf"] += part
    ordered = sorted(fused.values(), key=lambda e: (-e["rrf"], e["chunk_id"]))
    for rank, entry in enumerate(ordered, start=1):
        entry["rank"] = rank
    return ordered


def graph_expand(pool: Pool, seeds: list[str], vector: list[dict] | None) -> tuple[list[str], dict[str, list[dict]]]:
    """Follow validated REFERENCES edges one hop from the seed chunks' sections.

    Returns the chunks added (seed order, then edge order, at most
    MAX_GRAPH_CANDIDATES) and every path found, including paths to chunks
    that were already candidates.
    """
    vector_rank = {r["chunk_id"]: r["rank"] for r in vector or []}
    eligible = [pool.chunks[cid] for cid in pool.eligible]
    present, added = set(seeds), []
    paths: dict[str, list[dict]] = {}
    for seed in seeds:
        source = pool.chunks[seed]
        for edge in pool.references.get(source["section_id"], []):
            targets = [
                c for c in eligible
                if c["corpus_id"] == edge["corpus_id"] and c["policy_id"] == edge["target"]
                and (edge["target_section"] is None or section_number(c["heading_path"]) == edge["target_section"])
            ]
            targets.sort(key=lambda c: (vector_rank.get(c["chunk_id"], len(vector_rank) + 1), c["source_start"], c["chunk_id"]))
            if edge["target_section"] is None:
                targets = targets[:POLICY_REFERENCE_CHUNKS]
            for target in targets:
                cid = target["chunk_id"]
                paths.setdefault(cid, []).append({
                    "edge": "REFERENCES",
                    "hops": GRAPH_HOPS,
                    "from_chunk_id": seed,
                    "from_section_id": source["section_id"],
                    "target_policy_id": edge["target"],
                    "target_section": edge["target_section"],
                    "evidence": edge["evidence"],
                    "source_span": [edge["start"], edge["end"]],
                    "source_document_version_id": edge["document_version_id"],
                    "validation_status": "validated",
                })
                if cid not in present and len(added) < MAX_GRAPH_CANDIDATES:
                    present.add(cid)
                    added.append(cid)
    return added, paths


def rank_candidates(
    pool: Pool,
    question: str,
    mode: str,
    *,
    vector: list[dict] | None,
    reranker=None,
) -> tuple[list[dict], dict]:
    """Return the candidate pool in final order, each with its signals, and stage details."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    vector_by_id = {r["chunk_id"]: r for r in vector or []}
    keyword: list[dict] = []
    if mode != "vector":
        keyword = BM25Index(pool.eligible_chunks).search(question, CANDIDATE_K)
    keyword_by_id = {r["chunk_id"]: r for r in keyword}

    stages: dict = {}
    if mode == "vector":
        order = [r["chunk_id"] for r in (vector or [])[:CANDIDATE_K]]
    elif mode == "keyword":
        order = [r["chunk_id"] for r in keyword]
    else:
        fused = rrf_fuse((vector or [])[:VECTOR_K], keyword[:KEYWORD_K])
        fused_by_id = {e["chunk_id"]: e for e in fused}
        order = [e["chunk_id"] for e in fused][:MAX_RERANK_CANDIDATES]
        stages["rrf"] = {"k": RRF_K, "vector_k": VECTOR_K, "keyword_k": KEYWORD_K, "fused": len(fused)}

    graph_added: set[str] = set()
    graph_paths: dict[str, list[dict]] = {}
    if mode == "graph_rerank":
        added, graph_paths = graph_expand(pool, order, vector)
        graph_added = set(added)
        order = (order + added)[:MAX_RERANK_CANDIDATES]
        stages["graph"] = {
            "edge": "REFERENCES",
            "validation_status": "validated",
            "hops": GRAPH_HOPS,
            "max_added": MAX_GRAPH_CANDIDATES,
            "policy_reference_chunks": POLICY_REFERENCE_CHUNKS,
            "seeds": len(order) - len(added),
            "edges_in_generation": sum(len(v) for v in pool.references.values()),
            "added": added,
            "reached": sorted(graph_paths),
        }

    rerank_by_id: dict[str, dict] = {}
    if mode in RERANKED:
        if reranker is None:
            raise RetrievalRefused(f"{mode} needs the pinned reranker")
        started = time.perf_counter()
        records = reranker.score(question, [pool.chunks[cid] for cid in order])
        rerank_by_id = {r["chunk_id"]: r for r in records}
        order = [r["chunk_id"] for r in records]
        stages["rerank"] = {
            **reranker.identity,
            "candidates": len(records),
            "windowed": sum(1 for r in records if r["windows"] > 1),
            "timing_ms": round((time.perf_counter() - started) * 1000, 1),
            "score_meaning": "raw cross-encoder relevance logit; orders passages, not a probability",
        }

    candidates = []
    for rank, cid in enumerate(order, start=1):
        signals: dict = {"final_rank": rank}
        if cid in vector_by_id:
            v = vector_by_id[cid]
            signals.update(vector_rank=v["rank"], similarity=v["similarity"], exact_cosine=v["exact_cosine"])
        if cid in keyword_by_id:
            kw = keyword_by_id[cid]
            signals.update(
                keyword_rank=kw["rank"], bm25=kw["bm25"], boost=kw["boost"], exact_terms=kw["exact_terms"], keyword_score=kw["score"]
            )
        if mode in ("hybrid", *RERANKED) and cid in fused_by_id:
            entry = fused_by_id[cid]
            signals.update(rrf=entry["rrf"], rrf_parts=entry["rrf_parts"], rrf_rank=entry["rank"])
        if cid in graph_paths:
            signals.update(graph_added=cid in graph_added, graph_paths=graph_paths[cid])
        if cid in rerank_by_id:
            r = rerank_by_id[cid]
            signals.update(
                rerank_score=r["rerank_score"], rank_before_rerank=r["rank_before"], rerank_windows=r["windows"], pair_tokens=r["pair_tokens"]
            )
        candidates.append({"chunk_id": cid, "signals": signals})
    return candidates, stages


def linked_context(pool: Pool, chunk_id: str) -> dict:
    """Chunks that must travel with a hit, and the rest of its parent section.

    Mandatory: the other parts of a split passage, and the exception passage a
    rule refers to. The chunker records an exception reference before the
    exception's own chunk is complete, so a reference that names no chunk is
    resolved to the next part of the same section, where that exception starts.
    """
    chunk = pool.chunks[chunk_id]
    siblings = sorted(
        (c for c in pool.chunks.values() if c["section_id"] == chunk["section_id"] and c["chunk_id"] != chunk_id),
        key=lambda c: (c["source_start"], c["chunk_id"]),
    )
    mandatory: list[str] = []
    root = chunk.get("continuation_of") or chunk_id
    for sibling in siblings:
        if sibling["chunk_id"] == root or sibling.get("continuation_of") == root:
            mandatory.append(sibling["chunk_id"])
    for ref in chunk.get("exception_refs") or []:
        if ref in pool.chunks:
            target = ref
        else:
            later = [s for s in siblings if s["source_start"] > chunk["source_start"]]
            target = later[0]["chunk_id"] if later else None
        if target and target not in mandatory:
            mandatory.append(target)
    parent = [s["chunk_id"] for s in siblings if s["chunk_id"] not in mandatory]
    return {"mandatory": mandatory, "parent": parent}


def to_hit(pool: Pool, rank: int, candidate: dict) -> Hit:
    props = pool.chunks[candidate["chunk_id"]]
    signals = candidate["signals"]
    return Hit(
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
        source_spans=props["source_spans"],
        similarity=signals.get("similarity"),
        exact_cosine=signals.get("exact_cosine"),
        signals=signals,
        context=linked_context(pool, props["chunk_id"]),
    )


def context_chunks(pool: Pool, hits: list[Hit]) -> dict[str, dict]:
    """The linked chunks the answer stage may need, keyed by chunk id, without embeddings."""
    wanted = {cid for hit in hits for cid in hit.context["mandatory"] + hit.context["parent"]}
    fields = ("chunk_id", "document_version_id", "document_title", "corpus_id", "policy_id", "version",
              "publication_status", "effective_from", "effective_to", "section_id", "heading_path", "text", "source_spans")
    return {cid: {f: pool.chunks[cid].get(f) for f in fields} for cid in sorted(wanted)}


def search_pool(
    session,
    index: str,
    pool: Pool,
    embedder,
    question: str,
    *,
    mode: str = "vector",
    k: int = FINAL_K,
    reranker=None,
) -> dict:
    """Run one mode over a loaded pool. Shared by ask, evaluation, and the needle check."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    timing: dict[str, float] = {}
    vector, search, check, query_input = None, None, None, None
    if mode != "keyword":
        started = time.perf_counter()
        query_input = format_query(question)
        query_vector = embedder.embed([query_input])[0]
        timing["embed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        started = time.perf_counter()
        vector, search = vector_ranking(session, index, pool, query_vector)
        timing["vector_ms"] = round((time.perf_counter() - started) * 1000, 1)
        check = exact_check(vector, k)
    started = time.perf_counter()
    candidates, stages = rank_candidates(pool, question, mode, vector=vector, reranker=reranker)
    timing["rank_ms"] = round((time.perf_counter() - started) * 1000, 1)
    for candidate in candidates:
        props = pool.chunks[candidate["chunk_id"]]
        for key in ("document_version_id", "document_title", "heading_path", "source_spans"):
            candidate[key] = props[key]
    hits = [to_hit(pool, rank, c) for rank, c in enumerate(candidates[:k], start=1)]
    return {
        "mode": mode,
        "query_input": query_input,
        "k": k,
        "search": {
            **(search or {"method": "BM25 over the eligible chunks of the generation"}),
            "generation_chunks": len(pool.chunks),
            "eligible": len(pool.eligible),
            "excluded": pool.excluded,
            "stages": stages,
        },
        "exact_check": check,
        "candidates": candidates,
        "hits": [hit.as_dict() for hit in hits],
        "context_chunks": context_chunks(pool, hits),
        "stage_timing_ms": timing,
    }


def retrieve(
    session,
    index: str,
    embedder,
    question: str,
    snapshot_id: str,
    *,
    k: int = FINAL_K,
    as_of: str | None = None,
    include_history: bool = False,
    mode: str = "vector",
    reranker=None,
) -> dict:
    started = time.perf_counter()
    generation = published_generation(session, snapshot_id)
    check_compatible(generation, embedder)
    as_of, as_of_basis = resolve_as_of(session, generation, as_of)
    pool = load_pool(session, generation, as_of, include_history)
    result = search_pool(session, index, pool, embedder, question, mode=mode, k=k, reranker=reranker)
    return {
        **result,
        "snapshot_id": snapshot_id,
        "corpus_id": generation["corpus_id"],
        "index_generation_id": generation["id"],
        "as_of": as_of,
        "as_of_basis": as_of_basis,
        "include_history": include_history,
        "question": question,
        "embedder": embedder.identity,
        "timing_ms": round((time.perf_counter() - started) * 1000, 1),
    }
