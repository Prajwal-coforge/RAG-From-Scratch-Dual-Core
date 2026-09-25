"""Split policy text into section parents without dropping source offsets."""

from __future__ import annotations

import re
from dataclasses import dataclass

MD_HEADING = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
SECTION_HEADING = re.compile(r"^Section\s+(\d+)\s+[–—-]\s+(\S.*?)\s*$")
NUM_DOTTED = re.compile(r"^(\d+(?:\.\d+)*)\.\s+(\S.*?)\s*$")
NUM_BARE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s+(\S.*?)\s*$")


@dataclass(frozen=True)
class Section:
    section_id: str
    document_version_id: str
    document_title: str
    heading_path: str
    heading: str
    text: str
    body_start: int
    body_end: int


def parse_sections(
    text: str,
    *,
    document_version_id: str,
    document_title: str,
) -> list[Section]:
    """Parse Markdown or numbered headings. Each heading is its own parent."""
    headings = _headings(text)
    sections: list[Section] = []
    if not headings:
        body = text
        if body.strip():
            sections.append(
                _section(
                    text,
                    document_version_id,
                    document_title,
                    document_title,
                    document_title,
                    0,
                    len(text),
                )
            )
        return sections

    first = headings[0][0]
    if text[:first].strip():
        sections.append(
            _section(
                text,
                document_version_id,
                document_title,
                document_title,
                document_title,
                0,
                first,
            )
        )

    for index, (start, heading, _level) in enumerate(headings):
        line_end = text.find("\n", start)
        body_start = len(text) if line_end < 0 else line_end + 1
        body_end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        sections.append(
            _section(
                text,
                document_version_id,
                document_title,
                heading,
                heading,
                body_start,
                body_end,
            )
        )
    return sections


def _headings(text: str) -> list[tuple[int, str, int]]:
    found: list[tuple[int, str, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        md = MD_HEADING.match(stripped)
        section = SECTION_HEADING.match(stripped)
        numbered = _numbered_heading(stripped)
        if md and _looks_like_title(md.group(2)):
            found.append((offset, md.group(2), len(md.group(1))))
        elif section and _looks_like_title(section.group(2)):
            found.append((offset, f"Section {section.group(1)} {section.group(2)}", 1))
        elif numbered is not None:
            number, title = numbered
            found.append((offset, f"{number} {title}", number.count(".") + 1))
        offset += len(line)
    return found


def _numbered_heading(line: str) -> tuple[str, str] | None:
    match = NUM_DOTTED.match(line) or NUM_BARE.match(line)
    if match is None or not _looks_like_title(match.group(2)):
        return None
    return match.group(1), match.group(2)


def _looks_like_title(title: str) -> bool:
    words = title.split()
    if not words or len(words) > 12 or len(title) > 80:
        return False
    if title[-1] in ".:;":
        return False
    return title[0].isupper()


def _section(
    text: str,
    document_version_id: str,
    document_title: str,
    heading: str,
    heading_path: str,
    body_start: int,
    body_end: int,
) -> Section:
    return Section(
        section_id=f"{document_version_id}:{heading_path}",
        document_version_id=document_version_id,
        document_title=document_title,
        heading_path=heading_path,
        heading=heading,
        text=text,
        body_start=body_start,
        body_end=body_end,
    )
