"""Fetch the three pinned aviation files and verify them against the manifest."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

from app.corpus.generate import ROOT

MANIFEST = ROOT / "airport-policy-rag-spec" / "config" / "corpus-manifest.json"
SOURCE_ROOT = ROOT / "data" / "sources" / "imported"
LICENSE_URL = (
    "https://raw.githubusercontent.com/DecisionsDev/policy-corpus/"
    "948dacadbe03ca4d978ea3d6ccc19131e6a92efb/LICENSE"
)


class ChecksumMismatch(ValueError):
    pass


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text())


def import_sources(manifest: dict | None = None, source_root: Path = SOURCE_ROOT) -> list[dict]:
    """Download missing files, then verify every file. Nothing is executed or indexed here."""
    manifest = manifest or load_manifest()
    fetch_license(source_root)
    results = []
    for document in manifest["documents"]:
        path = source_root / document["path"]
        fetch_verified(document["source_url"], path, document["sha256"])
        results.append({"corpus_id": document["corpus_id"], "path": document["path"], "sha256": document["sha256"]})
    return results


def fetch_verified(url: str, path: Path, expected: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ChecksumMismatch(f"{path} sha256 {digest} does not match {expected}")
    if not path.exists():
        path.write_bytes(data)
    return data.decode("utf-8")


def fetch_license(source_root: Path = SOURCE_ROOT) -> Path:
    destination = source_root / "LICENSE"
    if not destination.exists():
        source_root.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(LICENSE_URL, timeout=60) as response:
            destination.write_bytes(response.read())
    return destination
