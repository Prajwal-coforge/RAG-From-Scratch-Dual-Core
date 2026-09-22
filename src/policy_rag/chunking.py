from __future__ import annotations

import re
from dataclasses import dataclass

from policy_rag.config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS

HEADING = re.compile(r"^(?P<num>\d+(?:\.\d+)*)\s+(?P<title>[A-Z“\"].{0,90})$")
CAPS_HEADING = re.compile(r"^(?P<title>[A-Z][A-Z0-9 ,/&-]{6,}):?\s*$")
LETTERED = re.compile(r"(?=\([a-z]\)\s)|(?=^[a-z]\.\s)", re.I | re.M)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
TOC_DOTS = re.compile(r"\.{3,}")


@dataclass
class Chunk:
    text: str
    name: str
    section: str
    version: str
    chunk_id: str

    def metadata(self) -> dict[str, str]:
        return {"name": self.name, "section": self.section, "version": self.version}


def _pack(parts: list[str], max_chars: int, overlap: int) -> list[str]:
    packed: list[str] = []
    buf = ""
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        candidate = f"{buf}\n{piece}".strip() if buf else piece
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            packed.append(buf)
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ""
            buf = f"{tail}\n{piece}".strip() if tail else piece
            if len(buf) > max_chars:
                packed.extend(_window(piece, max_chars, overlap))
                buf = packed.pop() if packed else piece[:max_chars]
        else:
            packed.extend(_window(piece, max_chars, overlap))
            buf = packed.pop() if packed else piece[:max_chars]
    if buf:
        packed.append(buf)
    return packed


def _window(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    start = 0
    step = max(max_chars - overlap, 1)
    while start < len(text):
        out.append(text[start : start + max_chars].strip())
        start += step
    return [c for c in out if c]


def split_oversized(text: str, max_chars: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    clauses = [p.strip() for p in LETTERED.split(text) if p.strip()]
    if len(clauses) > 1:
        return _pack(clauses, max_chars, overlap)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) > 1:
        return _pack(paras, max_chars, overlap)
    sentences = [s.strip() for s in SENTENCE.split(text) if s.strip()]
    if len(sentences) > 1:
        return _pack(sentences, max_chars, overlap)
    return _window(text, max_chars, overlap)


def split_sections(text: str) -> list[tuple[str, str, str]]:
    lines = text.splitlines()
    marks: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if TOC_DOTS.search(stripped):
            continue
        numbered = HEADING.match(stripped)
        if numbered:
            number = numbered.group("num")
            title = numbered.group("title").strip().rstrip(":")
            major = int(number.split(".")[0])
            words = title.split()
            if (
                1 <= major <= 40
                and 1 <= len(words) <= 12
                and not title.lower().startswith("version")
                and not title.lower().startswith("the ")
                and '"' not in title
                and "“" not in title
            ):
                marks.append((i, number, title))
            continue
        caps = CAPS_HEADING.match(stripped)
        if caps and "TABLE OF CONTENTS" not in stripped.upper():
            marks.append((i, "", caps.group("title").strip().rstrip(":")))
    if not marks:
        body = text.strip()
        return [("0.0", "Body", body)] if body else []
    sections: list[tuple[str, str, str]] = []
    for idx, (line_i, number, title) in enumerate(marks):
        start = line_i + 1
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        section_no = number or f"H{idx + 1}"
        sections.append((section_no, title, body))
    return sections


def chunk_document(
    text: str,
    name: str,
    version: str,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for number, title, body in split_sections(text):
        section = f"{number} {title}".strip()
        pieces = split_oversized(
            f"{section}\n{body}".strip() if body else section,
            max_chars,
            overlap,
        )
        for idx, piece in enumerate(pieces):
            chunk_id = f"{_slug(name)}::{number}::{idx}"
            chunks.append(
                Chunk(
                    text=piece,
                    name=name,
                    section=section,
                    version=version,
                    chunk_id=chunk_id,
                )
            )
    return chunks


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "doc"
