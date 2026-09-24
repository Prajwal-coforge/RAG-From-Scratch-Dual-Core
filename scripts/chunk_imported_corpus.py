"""Download the pinned aviation files and chunk them with EmbeddingGemma tokens."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

from app.chunking.chunk import ChunkConfig, chunk_document
from app.chunking.gguf_tokenizer import GemmaTokenizer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "airport-policy-rag-spec" / "config" / "corpus-manifest.json"
SOURCE_ROOT = ROOT / "data" / "sources" / "imported"
OUTPUT = ROOT / ".local" / "build" / "chunks" / "imported-chunks.jsonl"
SUMMARY = ROOT / ".local" / "build" / "chunks" / "imported-summary.json"
LICENSE_URL = (
    "https://raw.githubusercontent.com/DecisionsDev/policy-corpus/"
    "948dacadbe03ca4d978ea3d6ccc19131e6a92efb/LICENSE"
)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _fetch_license()
    tokenizer = GemmaTokenizer()
    config = ChunkConfig()
    summary = []
    with OUTPUT.open("w") as handle:
        for document in manifest["documents"]:
            path = SOURCE_ROOT / document["path"]
            text = _fetch_verified(document["source_url"], path, document["sha256"])
            version_id = f"{document['corpus_id']}:{document['sha256'][:12]}"
            children = chunk_document(
                text,
                document_version_id=version_id,
                document_title=document["policy_issuer"],
                access_policy_id=document["access_policy_id"],
                tokenizer=tokenizer,
                config=config,
            )
            headings = []
            for child in children:
                record = {
                    "corpus_id": document["corpus_id"],
                    "policy_issuer": document["policy_issuer"],
                    "document_version_id": child.document_version_id,
                    "heading_path": child.heading_path,
                    "parent_id": child.parent_id,
                    "chunk_id": child.chunk_id,
                    "access_policy_id": child.access_policy_id,
                    "token_count": child.token_count,
                    "overlap_tokens": child.overlap_tokens,
                    "source_start": child.source_start,
                    "source_end": child.source_end,
                    "part_index": child.part_index,
                    "continuation_of": child.continuation_of,
                    "exception_refs": list(child.exception_refs),
                    "reference_refs": list(child.reference_refs),
                    "table_header": child.table_header,
                    "embedding_input": child.embedding_input,
                    "text": child.text,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                headings.append(child.heading_path)
            over_max = [child.token_count for child in children if child.token_count > config.max_tokens]
            summary.append(
                {
                    "corpus_id": document["corpus_id"],
                    "issuer": document["policy_issuer"],
                    "sha256": document["sha256"],
                    "characters": len(text),
                    "children": len(children),
                    "sections": len(set(headings)),
                    "max_child_tokens": max((child.token_count for child in children), default=0),
                    "over_max": over_max,
                    "headings": sorted(set(headings)),
                }
            )
            print(
                f"{document['corpus_id']}: {len(set(headings))} sections, "
                f"{len(children)} children, max {summary[-1]['max_child_tokens']} tokens"
            )
    SUMMARY.write_text(json.dumps({"tokenizer": tokenizer.name, "documents": summary}, indent=2))
    print(f"wrote {OUTPUT}")


def _fetch_verified(url: str, path: Path, expected: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise SystemExit(f"{path} sha256 {digest} does not match {expected}")
    return data.decode("utf-8")


def _fetch_license() -> None:
    destination = SOURCE_ROOT / "LICENSE"
    if destination.exists():
        return
    with urllib.request.urlopen(LICENSE_URL, timeout=60) as response:
        destination.write_bytes(response.read())


if __name__ == "__main__":
    main()
