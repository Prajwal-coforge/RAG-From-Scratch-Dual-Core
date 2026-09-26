"""Snapshot loading and pre-publication quality checks.

A snapshot is one approved delivery of source documents: a generated-corpus
manifest under data/manifests, or one imported corpus from the pinned
upstream manifest (``imported:<corpus_id>``). Every document is loaded with
its declared metadata and its actual content hash, then checked before any
index generation is built from it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.chunking.parse import parse_sections

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = ROOT / "data" / "manifests"
IMPORTED_MANIFEST = ROOT / "airport-policy-rag-spec" / "config" / "corpus-manifest.json"
IMPORTED_ROOT = ROOT / "data" / "sources" / "imported"
GENERATED_SNAPSHOTS = ("clean", "duplicate", "dirty-stale", "historical")
STATUSES = ("active", "superseded", "draft", "retired")
REQUIRED = ("document_version_id", "policy_id", "version", "title", "content_sha256", "publication_status")

POLICY_ID_REF = re.compile(r"\b(AP-[A-Z]{3}-\d{3})(?:\s+section\s+(\d+(?:\.\d+)*))?")
NAMED_REF = re.compile(r"(?i)\brefer to (?:the )?((?:[A-Z][\w&-]*\s+){1,8}Policy)\b")


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SourceDocument:
    document_version_id: str
    corpus_id: str
    policy_issuer: str
    policy_id: str
    version: str
    title: str
    source_type: str
    source_uri: str
    path: str
    text: str
    content_sha256: str | None
    actual_sha256: str
    effective_from: str | None
    effective_to: str | None
    publication_status: str | None
    supersedes: str | None

    @property
    def document_title(self) -> str:
        """Title used in embedding and reranker input and in citations."""
        if self.source_type == "generated":
            return f"{self.policy_id} v{self.version} {self.title}"
        return f"{self.policy_issuer}: {self.title}"

    def metadata(self) -> dict:
        return {
            "document_version_id": self.document_version_id,
            "corpus_id": self.corpus_id,
            "policy_issuer": self.policy_issuer,
            "policy_id": self.policy_id,
            "version": self.version,
            "title": self.title,
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "path": self.path,
            "content_sha256": self.content_sha256,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "publication_status": self.publication_status,
            "supersedes": self.supersedes,
        }


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    document_version_id: str | None
    message: str

    def as_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "document_version_id": self.document_version_id,
            "message": self.message,
        }


@dataclass
class Snapshot:
    snapshot_id: str
    corpus_id: str
    as_of: str
    manifest_sha256: str
    documents: list[SourceDocument]
    evaluation_profile_only: bool = False
    fixture: dict | None = None
    notes: list[str] = field(default_factory=list)


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def available_snapshots() -> list[str]:
    imported = json.loads(IMPORTED_MANIFEST.read_text())
    return [*GENERATED_SNAPSHOTS, *(f"imported:{d['corpus_id']}" for d in imported["documents"])]


def load_snapshot(snapshot_id: str, *, manifest_dir: Path = MANIFEST_DIR) -> Snapshot:
    if snapshot_id.startswith("imported:"):
        return _load_imported(snapshot_id.split(":", 1)[1])
    path = manifest_dir / f"{snapshot_id}.json"
    if not path.is_file():
        raise SnapshotError(f"unknown snapshot {snapshot_id!r}; choose one of {', '.join(available_snapshots())}")
    raw = path.read_bytes()
    manifest = json.loads(raw)
    source_root = ROOT / manifest["source_root"]
    documents = []
    for entry in manifest["documents"]:
        file = source_root / entry["path"]
        data = file.read_bytes() if file.is_file() else b""
        documents.append(
            SourceDocument(
                document_version_id=entry.get("document_version_id") or "",
                corpus_id=manifest["corpus_id"],
                policy_issuer=manifest.get("policy_issuer", "AeroPolicy Airport"),
                policy_id=entry.get("policy_id") or "",
                version=str(entry["version"]) if entry.get("version") is not None else "",
                title=entry.get("title") or "",
                source_type="generated",
                source_uri=f"{manifest['source_root']}/{entry['path']}",
                path=str(file),
                text=data.decode("utf-8"),
                content_sha256=entry.get("content_sha256"),
                actual_sha256=sha256_bytes(data),
                effective_from=entry.get("effective_from"),
                effective_to=entry.get("effective_to"),
                publication_status=entry.get("publication_status"),
                supersedes=entry.get("supersedes"),
            )
        )
    fixture = manifest.get("fixture")
    return Snapshot(
        snapshot_id=snapshot_id,
        corpus_id=manifest["corpus_id"],
        as_of=manifest["as_of"],
        manifest_sha256=sha256_bytes(raw),
        documents=documents,
        evaluation_profile_only=bool(fixture and fixture.get("evaluation_profile_only")),
        fixture=fixture,
    )


def _load_imported(corpus_id: str) -> Snapshot:
    raw = IMPORTED_MANIFEST.read_bytes()
    manifest = json.loads(raw)
    entries = [d for d in manifest["documents"] if d["corpus_id"] == corpus_id]
    if not entries:
        raise SnapshotError(f"no imported corpus {corpus_id!r}")
    commit = manifest["commit"]
    documents = []
    for entry in entries:
        file = IMPORTED_ROOT / entry["path"]
        data = file.read_bytes() if file.is_file() else b""
        text = data.decode("utf-8")
        declared = entry.get("sha256")
        declared = f"sha256:{declared}" if declared and not declared.startswith("sha256:") else declared
        policy_id = Path(entry["path"]).stem
        documents.append(
            SourceDocument(
                document_version_id=f"{corpus_id}:{policy_id}:{(declared or '')[7:19]}",
                corpus_id=corpus_id,
                policy_issuer=entry["policy_issuer"],
                policy_id=policy_id,
                version=f"upstream@{commit[:8]}",
                title=_first_line(text),
                source_type="imported",
                source_uri=entry["source_url"],
                path=str(file),
                text=text,
                content_sha256=declared,
                actual_sha256=sha256_bytes(data),
                effective_from=entry.get("effective_from"),
                effective_to=entry.get("effective_to"),
                publication_status="active",
                supersedes=None,
            )
        )
    return Snapshot(
        snapshot_id=f"imported:{corpus_id}",
        corpus_id=corpus_id,
        as_of=date.today().isoformat(),
        manifest_sha256=sha256_bytes(raw),
        documents=documents,
        notes=["Imported sources have no authoritative effective dates; the pinned upstream copy is treated as the approved version."],
    )


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def validate_snapshot(snapshot: Snapshot) -> list[Finding]:
    findings: list[Finding] = []
    docs = snapshot.documents
    for doc in docs:
        findings.extend(_document_findings(doc))
    findings.extend(_version_conflicts(docs, snapshot.as_of))
    findings.extend(_duplicate_content(docs))
    findings.extend(_unresolved_references(docs))
    if snapshot.evaluation_profile_only:
        findings.append(
            Finding(
                "error",
                "evaluation_fixture",
                None,
                f"snapshot {snapshot.snapshot_id} is a damaged evaluation fixture: {snapshot.fixture.get('defect')}",
            )
        )
    return findings


def _document_findings(doc: SourceDocument) -> list[Finding]:
    found = []
    vid = doc.document_version_id or None
    meta = doc.metadata()
    for name in REQUIRED:
        if not meta.get(name):
            found.append(Finding("error", "missing_metadata", vid, f"required field {name} is missing"))
    if not doc.text:
        found.append(Finding("error", "missing_source", vid, f"source file {doc.source_uri} is missing or empty"))
    elif doc.content_sha256 and doc.content_sha256 != doc.actual_sha256:
        found.append(Finding("error", "hash_mismatch", vid, f"{doc.source_uri} hash {doc.actual_sha256} != declared {doc.content_sha256}"))
    if doc.publication_status and doc.publication_status not in STATUSES:
        found.append(Finding("error", "bad_status", vid, f"unknown publication_status {doc.publication_status!r}"))
    start, end = _parse_date(doc.effective_from, vid, "effective_from", found), _parse_date(doc.effective_to, vid, "effective_to", found)
    if start and end and end < start:
        found.append(Finding("error", "bad_dates", vid, f"effective_to {end} is before effective_from {start}"))
    if doc.effective_from is None:
        found.append(Finding("warning", "unknown_effective_dates", vid, "effective dates are unknown; the manifest's approved version is used"))
    if doc.publication_status == "superseded" and doc.effective_to is None:
        found.append(Finding("error", "bad_dates", vid, "a superseded version has no effective_to date"))
    return found


def _parse_date(value: str | None, vid: str | None, name: str, found: list[Finding]) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        found.append(Finding("error", "bad_dates", vid, f"{name} {value!r} is not an ISO date"))
        return None


def _version_conflicts(docs: list[SourceDocument], as_of: str) -> list[Finding]:
    found = []
    by_policy: dict[tuple[str, str], list[SourceDocument]] = {}
    for doc in docs:
        if doc.publication_status == "active":
            by_policy.setdefault((doc.corpus_id, doc.policy_id), []).append(doc)
    for (_corpus, policy_id), active in by_policy.items():
        if len(active) > 1:
            ids = ", ".join(d.document_version_id for d in active)
            found.append(Finding("error", "conflicting_active_versions", None, f"{policy_id} has {len(active)} active versions: {ids}"))
    for doc in docs:
        if doc.supersedes and doc.supersedes not in {d.document_version_id for d in docs}:
            found.append(Finding("warning", "supersedes_absent", doc.document_version_id, f"supersedes {doc.supersedes}, which is not in this snapshot"))
    return found


def _duplicate_content(docs: list[SourceDocument]) -> list[Finding]:
    seen: dict[str, str] = {}
    found = []
    for doc in docs:
        if not doc.text:
            continue
        if doc.actual_sha256 in seen:
            found.append(
                Finding("warning", "duplicate_content", doc.document_version_id, f"identical content to {seen[doc.actual_sha256]}; both identities are kept")
            )
        else:
            seen[doc.actual_sha256] = doc.document_version_id
    return found


def _unresolved_references(docs: list[SourceDocument]) -> list[Finding]:
    found = []
    policy_sections: dict[str, set[str]] = {}
    titles = {doc.title.lower() for doc in docs}
    for doc in docs:
        numbers = policy_sections.setdefault(doc.policy_id, set())
        for section in parse_sections(doc.text, document_version_id=doc.document_version_id, document_title=doc.title):
            head = section.heading.split(" ", 1)[0].rstrip(".")
            if head[:1].isdigit():
                numbers.add(head)
    for doc in docs:
        for match in POLICY_ID_REF.finditer(doc.text):
            target, section = match.group(1), match.group(2)
            if target == doc.policy_id:
                continue
            if target not in policy_sections:
                found.append(Finding("warning", "unresolved_reference", doc.document_version_id, f"references {target}, which is not in this snapshot"))
            elif section and section not in policy_sections[target]:
                found.append(Finding("warning", "unresolved_reference", doc.document_version_id, f"references {target} section {section}, which does not exist"))
        for match in NAMED_REF.finditer(doc.text):
            name = match.group(1).strip()
            if name.lower() not in titles:
                found.append(Finding("warning", "unresolved_reference", doc.document_version_id, f"refers to {name!r}, which is not in this snapshot"))
    return _unique(found)


def _unique(findings: list[Finding]) -> list[Finding]:
    return list(dict.fromkeys(findings))


def publication_decision(findings: list[Finding], *, profile: str, reason: str | None) -> tuple[bool, str]:
    errors = [f for f in findings if f.severity == "error"]
    if not errors:
        return True, "no blocking findings"
    if profile == "evaluation":
        if not reason or not reason.strip():
            return False, "the evaluation profile requires --reason"
        return True, f"{len(errors)} blocking finding(s) accepted under the evaluation profile: {reason.strip()}"
    return False, f"publication refused: {len(errors)} blocking finding(s)"
