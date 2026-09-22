#!/usr/bin/env python3
"""Build-loop steps 1–2: embed one text, then retrieve the right one of two."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from policy_rag.config import EMBED_MODEL, ollama_host
from policy_rag.embeddings import embed_documents, embed_query, ollama_available
from policy_rag.store import get_client, get_collection, query_vector, upsert_chunks


TEXTS = [
    "Whistleblowers should report concerns through dedicated reporting channels without fear of retribution.",
    "Dividend shall be paid out of the profits of the Company after providing for depreciation.",
]
QUERY = "How is dividend paid to shareholders?"


def main() -> int:
    if not ollama_available():
        print("Ollama is not reachable at", ollama_host())
        print("If it is running on your Mac, rerun with:")
        print("  export OLLAMA_HOST=http://host.docker.internal:11434")
        print("  python scripts/01_minimal_loop.py")
        return 1

    print("Ollama:", ollama_host())
    client = get_client()
    col = get_collection(client, name="minimal_loop", reset=True)

    print("1. Embedding and storing two known texts with", EMBED_MODEL)
    vectors = embed_documents(TEXTS)
    upsert_chunks(
        col,
        ids=["t1", "t2"],
        documents=TEXTS,
        embeddings=vectors,
        metadatas=[
            {"name": "Whistleblower Policy", "section": "8.0 Reporting a Concern", "version": "1.5"},
            {"name": "Dividend Distribution Policy", "section": "2.3", "version": "2"},
        ],
    )
    print(f"   stored {col.count()} chunks")

    print("2. Querying:", QUERY)
    q_vec = embed_query(QUERY)
    hits = query_vector(col, q_vec, n_results=2)
    ranked = (hits.get("documents") or [[]])[0]
    ids = (hits.get("ids") or [[]])[0]
    for rank, (doc_id, text) in enumerate(zip(ids, ranked), start=1):
        print(f"   [{rank}] {doc_id}: {text}")

    if not ranked:
        print("FAIL: no results")
        return 1
    if "Dividend" not in ranked[0]:
        print("FAIL: expected the dividend sentence first")
        return 1
    print("PASS: two-text retrieve loop ranked the dividend sentence first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
