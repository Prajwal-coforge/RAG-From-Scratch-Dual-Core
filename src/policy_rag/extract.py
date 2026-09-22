from __future__ import annotations

import re
from pathlib import Path

import pymupdf

PAGE_MARK = re.compile(r"^(?:-+|\u2013)\s*\d+\s+(?:of\s+\d+\s+)?(?:-+)?$|^-\s*\d+\s*-$|^Page\s+\d+$", re.I)
LONE_NUMBER = re.compile(r"^\d{1,3}$")
VERSION_RE = re.compile(r"Version\s*[:.]?\s*(v?[\d.]+)", re.I)
TOC_DOTS = re.compile(r"\.{3,}")
NUMBER_LINE = re.compile(r"^(\d+\.(?:\d+)*)\.?$|^(\d+)$")
TITLE_LINE = re.compile(r"^[A-Za-z“\"].{0,90}$")
BODY_START = re.compile(
    r"(?im)^(?:(?:1(?:\.0)?|1\.)\s+)?(Context|Preamble|PREAMBLE)\s*:?\s*$"
)

FILENAME_TITLES = (
    ("whistleblower", "Whistleblower Policy"),
    ("rpt", "Related Party Transactions Policy"),
    ("dividend", "Dividend Distribution Policy"),
    ("materiality", "Policy on Materiality of Events"),
)


def extract_pdf_text(path: str | Path) -> str:
    doc = pymupdf.open(path)
    pages: list[str] = []
    for page in doc:
        clip = page.rect + (0, 36, 0, -36)
        pages.append(page.get_text("text", clip=clip) or page.get_text("text"))
    doc.close()
    return "\n".join(pages)


def infer_title(filename: str, text: str) -> str:
    lower = Path(filename).name.lower()
    for key, title in FILENAME_TITLES:
        if key in lower:
            return title
    stem = Path(filename).stem.replace("-", " ").replace("_", " ")
    return re.sub(r"\s+\d+$", "", stem).strip() or "Policy"


def infer_version(text: str) -> str:
    matches = VERSION_RE.findall(text[:8000] + text[-2000:])
    return matches[-1] if matches else "unknown"


def _is_header(line: str, title: str | None) -> bool:
    if PAGE_MARK.match(line) or LONE_NUMBER.match(line):
        return True
    if title and line.lower() == title.lower():
        return True
    if line.lower() in {"coforge limited", "content", "s.no", "title", "page", "no"}:
        return True
    return False


def strip_headers_footers(text: str, title: str | None = None) -> list[str]:
    kept: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line or _is_header(line, title):
            continue
        kept.append(line)
    return kept


def merge_number_titles(lines: list[str]) -> list[str]:
    """Join '1.0' + 'Context:' and skip TOC rows whose next line is a page number."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        nxt2 = lines[i + 2] if i + 2 < len(lines) else ""
        num = NUMBER_LINE.match(line)
        if num and TITLE_LINE.match(nxt) and not TOC_DOTS.search(nxt):
            if LONE_NUMBER.match(nxt2):
                i += 3
                continue
            number = line.rstrip(".")
            out.append(f"{number} {nxt}")
            i += 2
            continue
        if TOC_DOTS.search(line):
            i += 1
            continue
        out.append(line)
        i += 1
    return out


def _last_body_start(text: str) -> re.Match[str] | None:
    match = None
    for match in BODY_START.finditer(text):
        if TOC_DOTS.search(match.group(0)):
            continue
    return match


def drop_front_matter(lines: list[str]) -> list[str]:
    text = "\n".join(lines)
    match = _last_body_start(text)
    if match:
        return text[match.start() :].splitlines()
    return lines


def load_policy(path: str | Path) -> dict[str, str]:
    path = Path(path)
    raw = extract_pdf_text(path)
    title = infer_title(path.name, raw)
    version = infer_version(raw)
    lines = drop_front_matter(merge_number_titles(strip_headers_footers(raw, title)))
    vh = next((i for i, ln in enumerate(lines) if re.search(r"VERSION HISTORY", ln, re.I)), None)
    if vh is not None:
        after = "\n".join(lines[vh + 1 :])
        resume = _last_body_start(after)
        lines = after[resume.start() :].splitlines() if resume else lines[:vh]
    return {
        "path": str(path),
        "name": title,
        "version": version,
        "text": "\n".join(lines),
        "raw": raw,
    }


def load_policies(directory: str | Path) -> list[dict[str, str]]:
    directory = Path(directory)
    return [load_policy(p) for p in sorted(directory.glob("*.pdf"))]
