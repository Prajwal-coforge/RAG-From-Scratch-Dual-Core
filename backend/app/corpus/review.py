"""Turn accepted raw drafts into the final reviewed documents.

Review edits live in review-edits.json, keyed by policy and pinned to the
raw draft's hash, so an edit can never silently land on a different draft.
Each edit must match exactly once, and the edited text must still pass the
draft checks. The raw draft on disk is never modified.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.corpus.generate import CATALOG, GENERATED, ROOT
from app.corpus.policies import BY_KEY
from app.corpus.validate import check_draft

EDITS = GENERATED / "review-edits.json"


class ReviewError(ValueError):
    pass


def apply_review(catalog_path: Path = CATALOG, edits_path: Path = EDITS, root: Path = ROOT) -> dict:
    catalog = json.loads(catalog_path.read_text())
    edits = json.loads(edits_path.read_text()) if edits_path.exists() else {}
    unknown = sorted(set(edits) - set(catalog["documents"]))
    if unknown:
        raise ReviewError(f"review edits for documents that are not in the catalog: {unknown}")
    source_dir = catalog_path.parent
    for key, entry in catalog["documents"].items():
        raw = (root / entry["generation"]["attempt_dir"] / "raw.md").read_text()
        if _sha(raw) != entry["generation"]["raw_sha256"]:
            raise ReviewError(f"{key}: raw draft on disk does not match the catalog")
        planned = edits.get(key, {"raw_sha256": entry["generation"]["raw_sha256"], "edits": []})
        if planned["raw_sha256"] != entry["generation"]["raw_sha256"]:
            raise ReviewError(f"{key}: review edits were written for a different draft")
        final = review_text(raw, planned["edits"])
        report = check_draft(final, BY_KEY[key])
        if not report.ok:
            raise ReviewError(f"{key}: reviewed text fails its checks: {report.problems}")
        (source_dir / entry["path"]).write_text(final)
        entry["content_sha256"] = _sha(final)
        entry["review"]["edits"] = planned["edits"]
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
    return catalog


def review_text(raw: str, edits: list[dict]) -> str:
    text = raw
    for edit in edits:
        count = text.count(edit["find"])
        if count != 1:
            raise ReviewError(f"edit {edit['find']!r} matches {count} times; it must match exactly once")
        text = text.replace(edit["find"], edit["replace"])
    return text.strip() + "\n"


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
