"""Deterministic policy graph links with source provenance.

REFERENCES     Section -> Policy, from an explicit policy identifier in the
               section text (optionally "section N"). Validated when the
               target policy, and the section if named, exist in the same
               corpus of the same snapshot. Otherwise recorded as unresolved
               and not written as an edge.
APPLIES_TO_ROLE Section -> Role, where a reviewed role name appears verbatim.
MAPS_TO_CONTROL Section -> Control, through a reviewed anchor sentence that
               occurs exactly once in the named section.
OWNED_BY       Policy -> Department, from the catalog owner field.

Nothing here is extracted by a model. Every section edge carries the
document version, the character span of its evidence, and its validation
status. Named references to documents outside the snapshot (for example
"refer to the SkyWings Airlines Dangerous Goods Policy") are unresolved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from app.sources import NAMED_REF, POLICY_ID_REF, ROOT

CONCEPTS = ROOT / "data" / "graph" / "concepts.json"
GRAPH_VERSION = "graph-v1"


@dataclass(frozen=True)
class Link:
    kind: str
    corpus_id: str
    document_version_id: str
    section_id: str
    target: str
    target_section: str | None
    start: int
    end: int
    evidence: str
    validation_status: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphPlan:
    links: list[Link]
    unresolved: list[dict]
    roles: list[dict]
    controls: list[dict]
    departments: list[dict]
    owned_by: list[dict]

    def counts(self) -> dict:
        kinds: dict[str, int] = {}
        for link in self.links:
            kinds[link.kind] = kinds.get(link.kind, 0) + 1
        return {**kinds, "OWNED_BY": len(self.owned_by), "unresolved": len(self.unresolved)}


def load_concepts() -> dict:
    return json.loads(CONCEPTS.read_text())


def concepts_sha256() -> str:
    return "sha256:" + hashlib.sha256(CONCEPTS.read_bytes()).hexdigest()


def section_number(heading: str) -> str | None:
    head = heading.strip().split(" ", 1)[0].rstrip(".")
    return head if head[:1].isdigit() else None


def _sentence(text: str, start: int, end: int) -> tuple[int, int]:
    left = max(text.rfind(". ", 0, start) + 2, text.rfind("\n", 0, start) + 1, 0)
    stop = [i for i in (text.find(". ", end), text.find("\n", end)) if i >= 0]
    right = min(stop) + 1 if stop else len(text)
    return left, right


def build_graph(documents, concepts: dict | None = None) -> GraphPlan:
    """documents: objects with .source (SourceDocument) and .sections (parsed sections)."""
    concepts = concepts if concepts is not None else load_concepts()
    by_policy: dict[tuple[str, str], set[str]] = {}
    titles: dict[str, set[str]] = {}
    for doc in documents:
        src = doc.source
        numbers = by_policy.setdefault((src.corpus_id, src.policy_id), set())
        numbers.update(n for n in (section_number(s.heading) for s in doc.sections) if n)
        titles.setdefault(src.corpus_id, set()).add(src.title.lower())

    links: list[Link] = []
    unresolved: list[dict] = []
    for doc in documents:
        src = doc.source
        for section in doc.sections:
            body = src.text[section.body_start : section.body_end]
            links.extend(_references(src, section, body, by_policy, unresolved))
            for match in NAMED_REF.finditer(body):
                name = match.group(1).strip()
                if name.lower() not in titles.get(src.corpus_id, set()):
                    start = section.body_start + match.start()
                    unresolved.append(
                        {"document_version_id": src.document_version_id, "section_id": section.section_id, "reference": name,
                         "start": start, "end": section.body_start + match.end(), "reason": "named document is not in this snapshot"}
                    )

    scoped = concepts.get("corpora", {})
    roles, controls, departments, owned_by = [], [], [], []
    present = {(doc.source.corpus_id, doc.source.policy_id) for doc in documents}
    for corpus_id, spec in scoped.items():
        corpus_docs = [doc for doc in documents if doc.source.corpus_id == corpus_id]
        if not corpus_docs:
            continue
        for role in spec.get("roles", []):
            used = False
            for doc in corpus_docs:
                for section in doc.sections:
                    body = doc.source.text[section.body_start : section.body_end]
                    at = body.find(role["name"])
                    if at < 0:
                        continue
                    used = True
                    start = section.body_start + at
                    s, e = _sentence(doc.source.text, start, start + len(role["name"]))
                    links.append(
                        Link("APPLIES_TO_ROLE", corpus_id, doc.source.document_version_id, section.section_id, role["id"], None,
                             s, e, doc.source.text[s:e].strip(), "exact-name-match")
                    )
            if used:
                roles.append({**role, "corpus_id": corpus_id})
        for control in spec.get("controls", []):
            anchored = False
            for anchor in control["anchors"]:
                doc = next((d for d in corpus_docs if d.source.document_version_id == anchor["document_version_id"]), None)
                if doc is None:
                    continue
                section = next((s for s in doc.sections if section_number(s.heading) == anchor["section"]), None)
                body = doc.source.text[section.body_start : section.body_end] if section else ""
                if section is None or body.count(anchor["anchor"]) != 1:
                    unresolved.append(
                        {"document_version_id": anchor["document_version_id"], "section": anchor["section"], "control": control["id"],
                         "reason": "control anchor is not found exactly once in the named section"}
                    )
                    continue
                anchored = True
                start = section.body_start + body.index(anchor["anchor"])
                links.append(
                    Link("MAPS_TO_CONTROL", corpus_id, doc.source.document_version_id, section.section_id, control["id"], None,
                         start, start + len(anchor["anchor"]), anchor["anchor"], "reviewed-anchor")
                )
            if anchored:
                controls.append({"id": control["id"], "name": control["name"], "corpus_id": corpus_id})
        for department in spec.get("departments", []):
            owners = [p for p in department["owns_policies"] if (corpus_id, p) in present]
            if owners:
                departments.append({"id": department["id"], "name": department["name"], "corpus_id": corpus_id,
                                    "provenance": department["provenance"]})
                owned_by.extend({"corpus_id": corpus_id, "policy_id": p, "department": department["id"]} for p in owners)
    return GraphPlan(links, unresolved, roles, controls, departments, owned_by)


def _references(src, section, body: str, by_policy, unresolved: list[dict]) -> list[Link]:
    links = []
    seen = set()
    for match in POLICY_ID_REF.finditer(body):
        target, target_section = match.group(1), match.group(2)
        if target == src.policy_id:
            continue
        start, end = section.body_start + match.start(), section.body_start + match.end()
        known = by_policy.get((src.corpus_id, target))
        if known is None:
            reason = f"{target} is not in this snapshot's {src.corpus_id} corpus"
        elif target_section and target_section not in known:
            reason = f"{target} has no section {target_section}"
        else:
            key = (target, target_section)
            if key in seen:
                continue
            seen.add(key)
            s, e = _sentence(src.text, start, end)
            links.append(
                Link("REFERENCES", src.corpus_id, src.document_version_id, section.section_id, target, target_section,
                     s, e, src.text[s:e].strip(), "validated")
            )
            continue
        unresolved.append(
            {"document_version_id": src.document_version_id, "section_id": section.section_id, "reference": match.group(0),
             "start": start, "end": end, "reason": reason}
        )
    return links
