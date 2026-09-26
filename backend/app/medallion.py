"""Bronze, silver, and gold file zones for one snapshot.

These zones are a record of the existing ingest path. They do not replace it.
Ingest still reads `data/sources` and `data/manifests` and still publishes
Memgraph generations. Nothing here is a data lake: there is no object store,
table format, or Spark job, and retrieval never reads these files.

- Bronze keeps the landed file identity (path, size, actual hash).
- Silver runs the same validation and publication gate as ingest.
- Gold, written only when that gate allows publication, is the chunk plan
  `build_plan` would publish, including the same generation id. Embeddings
  stay in the SQLite cache and in Memgraph.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ingest import build_plan
from app.sources import ROOT, load_snapshot, publication_decision, validate_snapshot

DEFAULT_ROOT = ROOT / ".local" / "medallion"


def zone_dir(snapshot_id: str) -> str:
    return snapshot_id.replace(":", "_")


def run_medallion(
    snapshot_id: str,
    embedder,
    *,
    profile: str = "ordinary",
    reason: str | None = None,
    root: Path = DEFAULT_ROOT,
) -> dict:
    snapshot = load_snapshot(snapshot_id)
    findings = validate_snapshot(snapshot)
    publishable, decision = publication_decision(findings, profile=profile, reason=reason)
    out = root / zone_dir(snapshot_id)
    out.mkdir(parents=True, exist_ok=True)

    bronze = {
        "zone": "bronze",
        "snapshot_id": snapshot.snapshot_id,
        "corpus_id": snapshot.corpus_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "documents": [
            {
                "document_version_id": doc.document_version_id,
                "source_uri": doc.source_uri,
                "path": doc.path,
                "bytes": len(doc.text.encode("utf-8")),
                "actual_sha256": doc.actual_sha256,
                "declared_sha256": doc.content_sha256,
            }
            for doc in snapshot.documents
        ],
    }
    silver = {
        "zone": "silver",
        "snapshot_id": snapshot.snapshot_id,
        "as_of": snapshot.as_of,
        "profile": profile,
        "publishable": publishable,
        "decision": decision,
        "findings": [finding.as_dict() for finding in findings],
        "documents": [doc.metadata() for doc in snapshot.documents],
    }
    gold = {
        "zone": "gold",
        "snapshot_id": snapshot.snapshot_id,
        "publishable": publishable,
        "generation_id": None,
        "chunks": [],
        "withheld_reason": None if publishable else decision,
    }
    if publishable:
        plan = build_plan(snapshot, embedder, profile=profile)
        gold["generation_id"] = plan.generation_id
        gold["chunks"] = [
            {
                "chunk_id": chunk.chunk_id,
                "document_version_id": chunk.document_version_id,
                "heading_path": chunk.heading_path,
                "token_count": chunk.token_count,
                "source_spans": [list(span) for span in chunk.spans],
                "text": chunk.text,
            }
            for chunk in plan.chunks
        ]

    _write(out / "bronze.json", bronze)
    _write(out / "silver.json", silver)
    _write(out / "gold.json", gold)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "output": str(out),
        "bronze_documents": len(bronze["documents"]),
        "silver_errors": sum(1 for finding in findings if finding.severity == "error"),
        "publishable": publishable,
        "decision": decision,
        "generation_id": gold["generation_id"],
        "gold_chunks": len(gold["chunks"]),
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")
