"""Needle retrieval check in an isolated index.

The published generation's chunks are copied, with their stored vectors, to
a separate label with its own vector index, and one made-up sentence is
added. Each mode is asked for it by its form code and by paraphrase, and the
needle's rank is recorded. The copy never gets a Publication pointer and is
deleted afterwards; the production index size is checked before and after.
"""

from __future__ import annotations

import json
import uuid

from app.embeddings import format_document
from app.retrieve import MODES, load_pool, published_generation, search_pool

LABEL = "NeedleChunk"
INDEX = "needle_embedding"
NEEDLE_ID = "needle-qx-7731"
NEEDLE_TITLE = "AP-NDL-900 v1 Evaluation Needle Note"
NEEDLE_HEADING = "1 Unattended Umbrellas"
NEEDLE_TEXT = (
    "Form QX-7731 must be lodged with the Lost Property Desk within 6 hours whenever staff find an "
    "unattended umbrella in the baggage hall."
)
QUERIES = {
    "by_code": "What does form QX-7731 require?",
    "paraphrase": "When an employee comes across an umbrella nobody has claimed in the baggage hall, what paperwork is due and how quickly?",
}


def _index_size(session, name: str) -> int | None:
    for row in session.run("CALL vector_search.show_index_info() YIELD * RETURN *").data():
        if row["index_name"] == name:
            return int(row["size"])
    return None


def _clean(session) -> None:
    if _index_size(session, INDEX) is not None:
        session.run(f"DROP VECTOR INDEX {INDEX}").consume()
    session.run(f"MATCH (n:{LABEL}) DETACH DELETE n").consume()
    # A vector index created before garbage collection indexes the deleted nodes too.
    session.run("FREE MEMORY").consume()


def run_needle(session, lock: dict, embedder, reranker, snapshot_id: str = "clean", modes=MODES) -> dict:
    production_index = lock["memgraph"]["vector_index"]
    production_before = _index_size(session, production_index)
    generation = published_generation(session, snapshot_id)
    rows = session.run("MATCH (c:Chunk {generation_id: $g}) RETURN properties(c) AS p", g=generation["id"]).data()
    needle_generation = f"needle-{uuid.uuid4().hex[:12]}"
    _clean(session)
    try:
        session.run(
            f"CREATE VECTOR INDEX {INDEX} ON :{LABEL}(embedding) "
            f'WITH CONFIG {{"dimension": {int(lock["memgraph"]["vector_dimension"])}, "capacity": {len(rows) + 16}, '
            f'"metric": "{lock["memgraph"]["vector_metric"]}"}}'
        ).consume()
        for row in rows:
            session.run(f"CREATE (:{LABEL} $p)", p={**row["p"], "generation_id": needle_generation}).consume()
        needle_input = format_document(f"{NEEDLE_TITLE} / {NEEDLE_HEADING}", NEEDLE_TEXT)
        needle = {
            **{k: v for k, v in rows[0]["p"].items() if k in ("corpus_id", "embedding_model", "embedding_revision")},
            "chunk_id": NEEDLE_ID,
            "generation_id": needle_generation,
            "document_version_id": "evaluation-needle:AP-NDL-900:v1",
            "document_title": NEEDLE_TITLE,
            "policy_id": "AP-NDL-900",
            "version": "1",
            "publication_status": "active",
            "effective_from": None,
            "effective_to": None,
            "section_id": "evaluation-needle:AP-NDL-900:v1#1",
            "heading_path": NEEDLE_HEADING,
            "text": NEEDLE_TEXT,
            "source_spans": json.dumps([[0, len(NEEDLE_TEXT)]]),
            "source_start": 0,
            "continuation_of": None,
            "exception_refs": [],
            "embedding": embedder.embed([needle_input])[0],
        }
        session.run(f"CREATE (:{LABEL} $p)", p=needle).consume()
        pool = load_pool(
            session,
            {"id": needle_generation, "chunk_count": len(rows) + 1},
            generation["as_of"],
            False,
            label=LABEL,
        )
        results = []
        for query_kind, question in QUERIES.items():
            for mode in modes:
                found = search_pool(session, INDEX, pool, embedder, question, mode=mode, reranker=reranker)
                ids = [c["chunk_id"] for c in found["candidates"]]
                rank = ids.index(NEEDLE_ID) + 1 if NEEDLE_ID in ids else None
                results.append(
                    {
                        "query": query_kind,
                        "question": question,
                        "mode": mode,
                        "needle_rank": rank,
                        "in_top_5": rank is not None and rank <= 5,
                        "candidates": len(ids),
                        "needle_signals": found["candidates"][rank - 1]["signals"] if rank else None,
                    }
                )
        published = session.run(
            "MATCH (p:Publication) WHERE p.current = $g OR p.previous = $g RETURN count(p) AS n", g=needle_generation
        ).single()["n"]
    finally:
        _clean(session)
    production_after = _index_size(session, production_index)
    leftover = session.run(f"MATCH (n:{LABEL}) RETURN count(n) AS n").single()["n"]
    return {
        "snapshot_id": snapshot_id,
        "copied_from_generation": generation["id"],
        "isolated_label": LABEL,
        "isolated_index": INDEX,
        "chunks": len(rows) + 1,
        "needle": {"chunk_id": NEEDLE_ID, "title": NEEDLE_TITLE, "heading": NEEDLE_HEADING, "text": NEEDLE_TEXT},
        "results": results,
        "isolation": {
            "publication_pointers_to_needle": published,
            "production_index_size": {"before": production_before, "after": production_after},
            "needle_nodes_left": leftover,
            "ok": published == 0 and production_before == production_after and leftover == 0,
        },
    }
