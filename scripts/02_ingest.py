#!/usr/bin/env python3
"""Extract, section-chunk, and store the policies/ PDFs in Chroma."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from policy_rag.chunking import chunk_document
from policy_rag.config import POLICIES_DIR, ollama_host
from policy_rag.embeddings import ollama_available
from policy_rag.extract import load_policies
from policy_rag.pipeline import ingest_chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policies", type=Path, default=POLICIES_DIR)
    parser.add_argument("--keep", action="store_true", help="append instead of resetting Chroma")
    args = parser.parse_args()

    if not ollama_available():
        print("Ollama is not reachable at", ollama_host())
        print("  export OLLAMA_HOST=http://host.docker.internal:11434")
        return 1

    docs = load_policies(args.policies)
    if not docs:
        print(f"No PDFs found in {args.policies}")
        return 1

    all_chunks = []
    for doc in docs:
        chunks = chunk_document(doc["text"], name=doc["name"], version=doc["version"])
        print(f"{doc['name']} v{doc['version']}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    n = ingest_chunks(all_chunks, reset=not args.keep)
    print(f"Ingested {n} chunks into Chroma")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
