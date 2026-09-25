"""Build the clean, duplicate, dirty-stale, and historical dataset manifests.

Manifests are derived from the reviewed catalog and are write-once. The
dirty-stale manifest is a simulated bad source delivery: the obsolete
AP-BAG-001 v1 is supplied as the active version and v2 is missing. The
document text is untouched; only the supplied catalog metadata is wrong,
and the exact field changes plus the original metadata are recorded.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from app.corpus.generate import CATALOG, GENERATED, ROOT
from app.corpus.policies import AS_OF, CORPUS_ID

MANIFESTS = ROOT / "data" / "manifests"
SUMS = MANIFESTS / "SHA256SUMS.json"
MANIFEST_FIELDS = (
    "document_version_id",
    "policy_id",
    "version",
    "title",
    "path",
    "content_sha256",
    "effective_from",
    "effective_to",
    "publication_status",
    "supersedes",
)

STALE_CORRUPTION = {
    "document_version_id": f"{CORPUS_ID}:AP-BAG-001:v1",
    "supplied": {"publication_status": "active", "effective_to": None},
}
STALE_MISSING = f"{CORPUS_ID}:AP-BAG-001:v2"


class ManifestError(ValueError):
    pass


def build_manifests(catalog: dict, source_dir: Path = GENERATED) -> dict[str, dict]:
    docs = catalog["documents"]
    for entry in docs.values():
        actual = _sha_file(source_dir / entry["path"])
        if actual != entry["content_sha256"]:
            raise ManifestError(f"{entry['path']} hash {actual} does not match the catalog")
    by_id = {entry["document_version_id"]: entry for entry in docs.values()}
    current = [e for e in docs.values() if e["publication_status"] == "active"]
    obsolete = [e for e in docs.values() if e["publication_status"] == "superseded"]

    stale_docs = []
    corruptions = []
    original = by_id[STALE_CORRUPTION["document_version_id"]]
    for entry in current:
        if entry["document_version_id"] == STALE_MISSING:
            continue
        stale_docs.append(_row(entry))
    supplied = _row(original)
    for field, value in STALE_CORRUPTION["supplied"].items():
        corruptions.append({"field": field, "original": original[field], "supplied": value})
        supplied[field] = value
    stale_docs.append(supplied)

    manifests = {
        "clean": _manifest("clean", "The three current AeroPolicy policies.", current),
        "duplicate": _manifest(
            "duplicate",
            "The three current policies plus the obsolete AP-BAG-001 v1, with correct metadata.",
            current + obsolete,
        ),
        "dirty-stale": _manifest(
            "dirty-stale",
            "Simulated stale source delivery for the diagnosis. Evaluation profile only.",
            [],
        ),
        "historical": _manifest(
            "historical",
            "Every version with correct dates. Used only when a question asks about history.",
            list(docs.values()),
        ),
    }
    stale = manifests["dirty-stale"]
    stale["documents"] = sorted(stale_docs, key=lambda row: row["document_version_id"])
    stale["fixture"] = {
        "kind": "stale-source-delivery",
        "evaluation_profile_only": True,
        "content_altered": False,
        "defect": (
            "The delivery supplies AP-BAG-001 v1 (30-minute escalation) marked active with no end date, "
            "and omits AP-BAG-001 v2 (10-minute escalation), which is the version in force on the as_of date."
        ),
        "missing_document_version_ids": [STALE_MISSING],
        "corruptions": [{"document_version_id": original["document_version_id"], **c} for c in corruptions],
        "original_metadata": _row(original),
    }
    for manifest in manifests.values():
        validate_manifest(manifest, source_dir)
    return manifests


def validate_manifest(manifest: dict, source_dir: Path = GENERATED) -> None:
    active: dict[str, list[str]] = {}
    for row in manifest["documents"]:
        if _sha_file(source_dir / row["path"]) != row["content_sha256"]:
            raise ManifestError(f"{manifest['manifest_id']}: {row['path']} does not match its hash")
        if row["publication_status"] == "active":
            active.setdefault(row["policy_id"], []).append(row["document_version_id"])
    conflicts = {policy: ids for policy, ids in active.items() if len(ids) > 1}
    if conflicts:
        raise ManifestError(f"{manifest['manifest_id']}: more than one active version: {conflicts}")


def write_manifests(manifests: dict[str, dict], out_dir: Path = MANIFESTS, force: bool = False) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sums = {}
    for name, manifest in manifests.items():
        path = out_dir / f"{name}.json"
        text = json.dumps(manifest, indent=2) + "\n"
        if path.exists() and path.read_text() != text and not force:
            raise ManifestError(f"{path.name} already exists with different content; manifests are write-once")
        path.write_text(text)
        sums[path.name] = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    (out_dir / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2) + "\n")
    return sums


def load_catalog(path: Path = CATALOG) -> dict:
    return json.loads(path.read_text())


def _manifest(name: str, purpose: str, entries: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "manifest_id": name,
        "corpus_id": CORPUS_ID,
        "purpose": purpose,
        "as_of": AS_OF,
        "source_root": "data/sources/generated",
        "documents": sorted((_row(e) for e in entries), key=lambda row: row["document_version_id"]),
        "fixture": None,
    }


def _row(entry: dict) -> dict:
    return copy.deepcopy({field: entry[field] for field in MANIFEST_FIELDS})


def _sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
