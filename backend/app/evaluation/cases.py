"""Evaluation cases, source clause labels, and the held-out freeze.

A clause label is an exact anchor sentence in one document version. A chunk
covers a clause when its source spans contain the whole anchor, so labels do
not change with the chunking configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.sources import ROOT, available_snapshots, load_snapshot

EVAL_ROOT = ROOT / "data" / "evaluation"
CLAUSES = EVAL_ROOT / "clauses.json"
SPLITS = ("dev", "heldout")
FREEZE = EVAL_ROOT / "heldout" / "FREEZE.json"
STATUSES = ("answered", "insufficient_evidence", "needs_clarification", "conflicting_sources")


class CaseError(ValueError):
    pass


@dataclass(frozen=True)
class Clause:
    clause_id: str
    document_version_id: str
    section: str
    anchor: str
    start: int
    end: int


@dataclass(frozen=True)
class Fact:
    fact_id: str
    patterns: tuple[str, ...]

    def matches(self, text: str) -> bool:
        return any(re.search(p, text, re.IGNORECASE) for p in self.patterns)


@dataclass(frozen=True)
class Case:
    case_id: str
    split: str
    corpus_kind: str
    corpus_id: str
    snapshot_id: str
    as_of: str | None
    include_history: bool
    question: str
    expected_status: str
    evidence_sets: tuple[tuple[str, ...], ...]
    required: tuple[Fact, ...]
    prohibited: tuple[Fact, ...]
    rationale: str


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def document_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for snapshot_id in available_snapshots():
        for doc in load_snapshot(snapshot_id).documents:
            texts.setdefault(doc.document_version_id, doc.text)
    return texts


def load_clauses(path: Path = CLAUSES, texts: dict[str, str] | None = None) -> dict[str, Clause]:
    texts = texts or document_texts()
    raw = json.loads(path.read_text())["clauses"]
    clauses = {}
    for clause_id, entry in raw.items():
        text = texts.get(entry["document_version_id"])
        if text is None:
            raise CaseError(f"{clause_id}: unknown document {entry['document_version_id']}")
        anchor = entry["anchor"]
        start = text.find(anchor)
        if start < 0:
            raise CaseError(f"{clause_id}: anchor not found verbatim in {entry['document_version_id']}")
        if text.find(anchor, start + 1) >= 0:
            raise CaseError(f"{clause_id}: anchor occurs more than once")
        clauses[clause_id] = Clause(clause_id, entry["document_version_id"], entry["section"], anchor, start, start + len(anchor))
    return clauses


def load_cases(split: str, clauses: dict[str, Clause] | None = None) -> list[Case]:
    if split not in SPLITS:
        raise CaseError(f"unknown split {split!r}")
    clauses = clauses or load_clauses()
    raw = json.loads((EVAL_ROOT / split / "cases.json").read_text())
    cases = []
    seen = set()
    snapshots = set(available_snapshots())
    for entry in raw["cases"]:
        case = Case(
            case_id=entry["id"],
            split=split,
            corpus_kind=entry["corpus_kind"],
            corpus_id=entry["corpus_id"],
            snapshot_id=entry["snapshot_id"],
            as_of=entry["as_of"],
            include_history=bool(entry["include_history"]),
            question=entry["question"],
            expected_status=entry["expected_status"],
            evidence_sets=tuple(tuple(s) for s in entry["acceptable_evidence_sets"]),
            required=tuple(Fact(f["id"], tuple(f["patterns"])) for f in entry["required_answer_facts"]),
            prohibited=tuple(Fact(f["id"], tuple(f["patterns"])) for f in entry["prohibited_answer_facts"]),
            rationale=entry["rationale"],
        )
        _check_case(case, clauses, snapshots)
        if case.case_id in seen:
            raise CaseError(f"duplicate case id {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)
    return cases


def _check_case(case: Case, clauses: dict[str, Clause], snapshots: set[str]) -> None:
    where = case.case_id
    if case.snapshot_id not in snapshots:
        raise CaseError(f"{where}: unknown snapshot {case.snapshot_id}")
    if case.expected_status not in STATUSES:
        raise CaseError(f"{where}: unknown status {case.expected_status}")
    if case.corpus_kind not in ("generated", "imported"):
        raise CaseError(f"{where}: corpus_kind must be generated or imported")
    for evidence in case.evidence_sets:
        for clause_id in evidence:
            if clause_id not in clauses:
                raise CaseError(f"{where}: unknown clause {clause_id}")
    for fact in (*case.required, *case.prohibited):
        for pattern in fact.patterns:
            re.compile(pattern)
    if case.expected_status == "answered":
        if not case.evidence_sets or not case.required:
            raise CaseError(f"{where}: an answered case needs evidence and required facts")
        for evidence in case.evidence_sets:
            source = " ".join(clauses[c].anchor for c in evidence)
            for fact in case.required:
                if not fact.matches(source):
                    raise CaseError(f"{where}: required fact {fact.fact_id} is not in the labelled clauses")
            for fact in case.prohibited:
                if fact.matches(source):
                    raise CaseError(f"{where}: prohibited fact {fact.fact_id} appears in the labelled clauses")
    elif case.required:
        raise CaseError(f"{where}: an abstention case cannot require answer facts")


def freeze_record() -> dict:
    return {
        "heldout_cases": sha256_file(EVAL_ROOT / "heldout" / "cases.json"),
        "clauses": sha256_file(CLAUSES),
    }


def check_freeze() -> dict:
    if not FREEZE.is_file():
        raise CaseError("the held-out suite has not been frozen")
    frozen = json.loads(FREEZE.read_text())
    current = freeze_record()
    for key, digest in current.items():
        if frozen["hashes"][key] != digest:
            raise CaseError(f"{key} changed after the freeze ({frozen['hashes'][key]} -> {digest})")
    return frozen
