#!/usr/bin/env python3
"""Print hybrid-retrieved policy chunks. No generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from policy_rag.pipeline import retrieve


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+")
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    question = " ".join(args.question)

    hits = retrieve(question, use_rerank=not args.no_rerank)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": h.id,
                        "name": h.metadata.get("name"),
                        "section": h.metadata.get("section"),
                        "version": h.metadata.get("version"),
                        "score": h.score,
                        "source": h.source,
                        "text": h.text,
                    }
                    for h in hits
                ],
                indent=2,
            )
        )
        return 0

    if not hits:
        print("No chunks retrieved.")
        return 1
    for i, hit in enumerate(hits, start=1):
        print(f"[{i}] {hit.metadata.get('name')} · {hit.metadata.get('section')}")
        print(f"    source={hit.source}  score={hit.score:.4f}")
        print(hit.text[:500])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
