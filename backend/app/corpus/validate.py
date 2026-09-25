"""Checks a generated policy draft must pass before it can be accepted."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.corpus.policies import PolicySpec

MIN_WORDS = 500
MAX_WORDS = 800
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’./-]*")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
LIST_OR_TABLE = re.compile(r"^\s*(?:[-*+•]\s|\d+[.)]\s|\|)")
POLICY_ID = re.compile(r"\bAP-[A-Z]{3}-\d{3}\b")


@dataclass
class DraftReport:
    prose_words: int
    headings: list[str]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def normalize_space(text: str) -> str:
    return " ".join(text.split())


def prose_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not HEADING.match(line)]


def count_prose_words(text: str) -> int:
    """Words outside headings. There is no front matter in the document files."""
    return sum(len(WORD.findall(line)) for line in prose_lines(text))


def check_draft(text: str, spec: PolicySpec) -> DraftReport:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    headings = [HEADING.match(line).group(1) for line in lines if HEADING.match(line)]
    report = DraftReport(prose_words=count_prose_words(text), headings=headings)
    problems = report.problems

    if not lines or lines[0] != spec.heading:
        problems.append(f"first line must be {spec.heading!r}")
    if headings[1:] != list(spec.sections):
        problems.append(f"section headings {headings[1:]} do not match {list(spec.sections)}")
    if not MIN_WORDS <= report.prose_words <= MAX_WORDS:
        problems.append(f"{report.prose_words} prose words, outside {MIN_WORDS}-{MAX_WORDS}")

    flat = normalize_space(text)
    for clause in spec.verbatim:
        if normalize_space(clause) not in flat:
            problems.append(f"missing required clause: {clause[:60]}...")
    for reference in spec.references:
        if reference not in flat:
            problems.append(f"missing reference to {reference}")
    for phrase in spec.forbidden:
        if phrase.lower() in flat.lower():
            problems.append(f"contains forbidden phrase {phrase!r}")
    unknown = sorted(set(POLICY_ID.findall(flat)) - {spec.policy_id, *spec.references})
    if unknown:
        problems.append(f"references policies that do not exist: {unknown}")

    if any(LIST_OR_TABLE.match(line) for line in prose_lines(text)):
        problems.append("contains list items or table rows; the documents are prose")
    if "<think>" in text or "</think>" in text:
        problems.append("contains model reasoning tags")
    if re.search(r"\b(?:19|20)\d{2}\b", flat) or re.search(r"(?i)\bversion\s+\d", flat):
        problems.append("states a date or version; those belong to the catalog metadata")
    return report
