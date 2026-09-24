"""Parent sections, child passages, sentence overlap, and rerank windows.

Token counts come from the tokenizer passed in. A word counter is not
EmbeddingGemma. Defaults are target 300, maximum 400, overlap 50.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from app.chunking.parse import Section, parse_sections
from app.chunking.tokenizer import Tokenizer

SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])")
EXCEPTION = re.compile(r"(?i)(?:^\s*exception\b|\b(?:except|unless)\b|\bexception applies\b)")
REFERENCE = re.compile(r"(?i)\b(?:refer to|see section|see the)\b[^.\n]{0,160}")
TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


class ChunkOverflow(ValueError):
    """A piece cannot fit the hard token limit, and the text was not truncated."""


@dataclass(frozen=True)
class ChunkConfig:
    target_tokens: int = 300
    max_tokens: int = 400
    overlap_tokens: int = 50
    rerank_pair_tokens: int = 512
    rerank_special_tokens: int = 3
    strategy: str = "section-aware-parent-child"

    def __post_init__(self) -> None:
        if self.target_tokens < 1 or self.max_tokens < self.target_tokens:
            raise ValueError("token limits must satisfy 1 <= target <= max")
        if self.overlap_tokens < 0:
            raise ValueError("overlap cannot be negative")

    def fingerprint(self, tokenizer_name: str) -> str:
        payload = {
            "strategy": self.strategy,
            "target_tokens": self.target_tokens,
            "max_tokens": self.max_tokens,
            "overlap_tokens": self.overlap_tokens,
            "tokenizer": tokenizer_name,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class ChildChunk:
    chunk_id: str
    parent_id: str
    document_version_id: str
    document_title: str
    heading_path: str
    text: str
    spans: tuple[tuple[int, int], ...]
    access_policy_id: str
    token_count: int
    overlap_tokens: int
    part_index: int
    continuation_of: str | None
    exception_refs: tuple[str, ...]
    reference_refs: tuple[str, ...]
    table_header: str | None
    embedding_input: str
    chunker_config_hash: str

    @property
    def source_start(self) -> int:
        return self.spans[0][0]

    @property
    def source_end(self) -> int:
        return self.spans[-1][1]


@dataclass(frozen=True)
class RerankWindow:
    chunk_id: str
    part_index: int
    text: str
    spans: tuple[tuple[int, int], ...]
    token_count: int
    continuation_of: str | None


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    kind: str
    spans: tuple[tuple[int, int], ...] = ()
    table_header: str | None = None
    rendered: str = ""
    overlap_tokens: int = 0


def chunk_document(
    text: str,
    *,
    document_version_id: str,
    document_title: str,
    access_policy_id: str,
    tokenizer: Tokenizer,
    config: ChunkConfig | None = None,
    access_by_heading: dict[str, str] | None = None,
) -> list[ChildChunk]:
    settings = config or ChunkConfig()
    sections = parse_sections(
        text,
        document_version_id=document_version_id,
        document_title=document_title,
        access_policy_id=access_policy_id,
        access_by_heading=access_by_heading,
    )
    children: list[ChildChunk] = []
    for section in sections:
        children.extend(chunk_section(section, tokenizer, settings))
    return children


def chunk_section(section: Section, tokenizer: Tokenizer, config: ChunkConfig) -> list[ChildChunk]:
    body = section.text[section.body_start : section.body_end]
    if tokenizer.count(body) == 0:
        return []
    config_hash = config.fingerprint(tokenizer.name)
    if tokenizer.count(body) <= config.max_tokens and not _contains_table(body):
        return [
            _child(
                section,
                body,
                ((section.body_start, section.body_end),),
                tokenizer,
                config_hash,
                overlap_tokens=0,
                part_index=0,
                continuation_of=None,
                exception_refs=(),
                table_header=None,
            )
        ]

    units = _units(section, tokenizer, config.max_tokens)
    packed = _pack(section, units, tokenizer, config)
    return [
        _child(
            section,
            piece.rendered,
            piece.spans,
            tokenizer,
            config_hash,
            overlap_tokens=piece.overlap_tokens,
            part_index=piece.part_index,
            continuation_of=piece.continuation_of,
            exception_refs=piece.exception_refs,
            table_header=piece.table_header,
        )
        for piece in packed
    ]


@dataclass(frozen=True)
class _Piece:
    rendered: str
    spans: tuple[tuple[int, int], ...]
    overlap_tokens: int
    part_index: int
    continuation_of: str | None
    exception_refs: tuple[str, ...]
    table_header: str | None


def split_rerank_windows(
    chunk: ChildChunk,
    question: str,
    tokenizer: Tokenizer,
    config: ChunkConfig | None = None,
) -> list[RerankWindow]:
    """Split a child that fits embeddings but overflows the reranker pair limit."""
    settings = config or ChunkConfig()
    prefix = f"{chunk.document_title} {chunk.heading_path}"
    overhead = settings.rerank_special_tokens + tokenizer.count(question) + tokenizer.count(prefix)
    passage_budget = settings.rerank_pair_tokens - overhead
    if passage_budget < 1:
        raise ChunkOverflow("question and heading leave no room for policy text in the reranker")
    pair_tokens = overhead + tokenizer.count(chunk.text)
    if pair_tokens <= settings.rerank_pair_tokens:
        return [
            RerankWindow(chunk.chunk_id, 0, chunk.text, chunk.spans, tokenizer.count(chunk.text), None)
        ]

    windows: list[RerankWindow] = []
    for part_index, (text, spans) in enumerate(_windows_for_text(chunk.text, chunk.spans, tokenizer, passage_budget)):
        first_id = windows[0].chunk_id if windows else None
        windows.append(
            RerankWindow(
                chunk_id=f"{chunk.chunk_id}:rerank:{part_index}",
                part_index=part_index,
                text=text,
                spans=spans,
                token_count=tokenizer.count(text),
                continuation_of=first_id,
            )
        )
    return windows


def _child(
    section: Section,
    rendered: str,
    spans: tuple[tuple[int, int], ...],
    tokenizer: Tokenizer,
    config_hash: str,
    *,
    overlap_tokens: int,
    part_index: int,
    continuation_of: str | None,
    exception_refs: tuple[str, ...],
    table_header: str | None,
) -> ChildChunk:
    span_key = ",".join(f"{start}:{end}" for start, end in spans)
    identity = f"{section.document_version_id}|{span_key}|{part_index}|{config_hash}"
    chunk_id = hashlib.sha256(identity.encode()).hexdigest()
    title_and_section = f"{section.document_title} / {section.heading_path}"
    return ChildChunk(
        chunk_id=chunk_id,
        parent_id=section.section_id,
        document_version_id=section.document_version_id,
        document_title=section.document_title,
        heading_path=section.heading_path,
        text=rendered,
        spans=spans,
        access_policy_id=section.access_policy_id,
        token_count=tokenizer.count(rendered),
        overlap_tokens=overlap_tokens,
        part_index=part_index,
        continuation_of=continuation_of,
        exception_refs=exception_refs,
        reference_refs=tuple(dict.fromkeys(REFERENCE.findall(rendered))),
        table_header=table_header,
        embedding_input=f"title: {title_and_section} | text: {rendered}",
        chunker_config_hash=config_hash,
    )


def _units(section: Section, tokenizer: Tokenizer, max_tokens: int) -> list[_Unit]:
    body = section.text[section.body_start : section.body_end]
    units: list[_Unit] = []
    for start, end in _blocks(body):
        absolute_start = section.body_start + start
        absolute_end = section.body_start + end
        block = body[start:end]
        table = _table_groups(section.text, absolute_start, absolute_end, tokenizer, max_tokens)
        if table is not None:
            units.extend(table)
            continue
        for sent_start, sent_end in _sentence_spans(block):
            sentence = block[sent_start:sent_end]
            kind = "exception" if EXCEPTION.search(sentence) else "sentence"
            units.append(_Unit(absolute_start + sent_start, absolute_start + sent_end, kind))
    return units


def _pack(section: Section, units: list[_Unit], tokenizer: Tokenizer, config: ChunkConfig) -> list[_Piece]:
    pieces: list[_Piece] = []
    current: list[_Unit] = []

    def flush(extra_refs: tuple[str, ...] = ()) -> None:
        if not current:
            return
        rendered, spans, header = _render(section.text, current)
        pieces.append(
            _Piece(
                rendered,
                spans,
                current[0].overlap_tokens,
                0,
                None,
                extra_refs,
                header,
            )
        )
        current.clear()

    for unit in units:
        if unit.kind == "table_group":
            flush()
            pieces.append(_Piece(unit.rendered, unit.spans, 0, 0, None, (), unit.table_header))
            continue
        rendered_unit = section.text[unit.start : unit.end]
        if tokenizer.count(rendered_unit) > config.max_tokens:
            flush()
            pieces.extend(_subspan_pieces(section, unit, tokenizer, config))
            continue
        if unit.kind == "exception" and current:
            candidate, _, _ = _render(section.text, current + [unit])
            if tokenizer.count(candidate) <= config.max_tokens:
                current.append(unit)
                continue
            exception_id = _span_id(section, ((unit.start, unit.end),), 0, tokenizer, config)
            flush((exception_id,))
            current.append(unit)
            continue
        if not current:
            current.append(unit)
            continue
        candidate, _, _ = _render(section.text, current + [unit])
        if tokenizer.count(candidate) <= config.target_tokens:
            current.append(unit)
            continue
        flush()
        current.extend(_with_overlap(section.text, pieces, unit, tokenizer, config))

    flush()
    return pieces


def _with_overlap(
    text: str,
    pieces: list[_Piece],
    unit: _Unit,
    tokenizer: Tokenizer,
    config: ChunkConfig,
) -> list[_Unit]:
    if not pieces or config.overlap_tokens == 0 or pieces[-1].table_header is not None:
        return [unit]
    previous = pieces[-1]
    if len(previous.spans) != 1:
        return [unit]
    overlap_start = _overlap_start(text, previous.spans[0][0], previous.spans[0][1], tokenizer, config.overlap_tokens)
    if overlap_start is None or overlap_start >= unit.start:
        return [unit]
    overlap_tokens = tokenizer.count(text[overlap_start:unit.start])
    overlapped = _Unit(overlap_start, unit.end, unit.kind, overlap_tokens=overlap_tokens)
    if tokenizer.count(text[overlapped.start : overlapped.end]) <= config.max_tokens:
        return [overlapped]
    return [unit]


def _span_id(
    section: Section,
    spans: tuple[tuple[int, int], ...],
    part_index: int,
    tokenizer: Tokenizer,
    config: ChunkConfig,
) -> str:
    span_key = ",".join(f"{start}:{end}" for start, end in spans)
    config_hash = config.fingerprint(tokenizer.name)
    identity = f"{section.document_version_id}|{span_key}|{part_index}|{config_hash}"
    return hashlib.sha256(identity.encode()).hexdigest()


def _overlap_start(text: str, start: int, end: int, tokenizer: Tokenizer, limit: int) -> int | None:
    sentences = _sentence_spans(text[start:end])
    if not sentences or limit <= 0:
        return None
    chosen: int | None = None
    for sent_start, _sent_end in reversed(sentences):
        absolute = start + sent_start
        if tokenizer.count(text[absolute:end]) <= limit:
            chosen = absolute
        else:
            break
    return chosen


def _subspan_pieces(section: Section, unit: _Unit, tokenizer: Tokenizer, config: ChunkConfig) -> list[_Piece]:
    source = section.text
    slices = list(_token_slices(source[unit.start : unit.end], tokenizer, config.max_tokens))
    pieces: list[_Piece] = []
    cursor = unit.start
    first_id: str | None = None
    for part_index, (local_start, local_end) in enumerate(slices):
        start = unit.start + local_start
        end = unit.start + local_end
        if source[cursor:start].strip():
            raise ChunkOverflow("subspan slices left a gap in an over-limit sentence")
        cursor = end
        rendered = source[start:end]
        chunk_key = _span_id(section, ((start, end),), part_index, tokenizer, config)
        if part_index == 0:
            first_id = chunk_key
        pieces.append(
            _Piece(
                rendered,
                ((start, end),),
                0,
                part_index,
                None if part_index == 0 else first_id,
                (),
                None,
            )
        )
    if source[cursor:unit.end].strip():
        raise ChunkOverflow("subspan slices did not cover the over-limit sentence")
    return pieces


def _render(text: str, units: list[_Unit]) -> tuple[str, tuple[tuple[int, int], ...], str | None]:
    spans: list[tuple[int, int]] = []
    parts: list[str] = []
    header: str | None = None
    for unit in units:
        if unit.kind == "table_group":
            parts.append(unit.rendered)
            spans.extend(unit.spans)
            header = unit.table_header
            continue
        parts.append(text[unit.start : unit.end])
        if spans and spans[-1][1] == unit.start:
            spans[-1] = (spans[-1][0], unit.end)
        else:
            spans.append((unit.start, unit.end))
    return "\n".join(parts) if header else _join_original(text, spans), tuple(spans), header


def _join_original(text: str, spans: list[tuple[int, int]]) -> str:
    if len(spans) == 1:
        return text[spans[0][0] : spans[0][1]]
    return "\n".join(text[start:end] for start, end in spans)


def _blocks(body: str) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    cursor = 0
    for match in re.finditer(r"\n\s*\n", body):
        if match.start() > cursor and body[cursor : match.start()].strip():
            blocks.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(body) and body[cursor:].strip():
        blocks.append((cursor, len(body)))
    return blocks


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    if not text.strip():
        return []
    breaks = [match.start() for match in SENTENCE_BREAK.finditer(text)]
    spans: list[tuple[int, int]] = []
    start = 0
    for index in breaks:
        end = index
        while end > start and text[end - 1].isspace():
            end -= 1
        if text[start:end].strip():
            spans.append((start, end))
        start = index
        while start < len(text) and text[start].isspace():
            start += 1
    if text[start:].strip():
        spans.append((start, _trim_end(text, start)))
    return spans


def _trim_end(text: str, start: int) -> int:
    end = len(text)
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def _contains_table(body: str) -> bool:
    return any(TABLE_RULE.match(line) for line in body.splitlines())


def _table_groups(
    text: str,
    start: int,
    end: int,
    tokenizer: Tokenizer,
    max_tokens: int,
) -> list[_Unit] | None:
    block = text[start:end]
    lines = block.splitlines(keepends=True)
    if not any(TABLE_RULE.match(line) for line in lines):
        return None
    header_lines: list[str] = []
    rows: list[tuple[int, int, str]] = []
    cursor = start
    seen_rule = False
    header_end = start
    for line in lines:
        line_end = cursor + len(line)
        if not seen_rule and (TABLE_ROW.match(line) or TABLE_RULE.match(line)):
            header_lines.append(line)
            header_end = line_end
            seen_rule = seen_rule or TABLE_RULE.match(line) is not None
        elif seen_rule and TABLE_ROW.match(line):
            rows.append((cursor, line_end, line))
        cursor = line_end
    if not rows:
        return None
    header = "".join(header_lines).strip()
    groups: list[_Unit] = []
    bucket: list[tuple[int, int]] = []
    for row_start, row_end, _line in rows:
        trial_rows = bucket + [(row_start, row_end)]
        rendered = _table_text(text, start, header_end, trial_rows)
        if bucket and tokenizer.count(rendered) > max_tokens:
            groups.append(_table_unit(text, start, header_end, bucket, header))
            bucket = [(row_start, row_end)]
            single = _table_text(text, start, header_end, bucket)
            if tokenizer.count(single) > max_tokens:
                raise ChunkOverflow("a table row plus its header exceeds the hard token limit")
        else:
            bucket = trial_rows
    if bucket:
        groups.append(_table_unit(text, start, header_end, bucket, header))
    return groups


def _table_text(text: str, header_start: int, header_end: int, rows: list[tuple[int, int]]) -> str:
    header = text[header_start:header_end].strip()
    body = "\n".join(text[start:end].strip() for start, end in rows)
    return f"{header}\n{body}"


def _table_unit(
    text: str,
    header_start: int,
    header_end: int,
    rows: list[tuple[int, int]],
    header: str,
) -> _Unit:
    spans = ((header_start, header_end), *rows)
    return _Unit(
        header_start,
        rows[-1][1],
        "table_group",
        spans=spans,
        table_header=header,
        rendered=_table_text(text, header_start, header_end, rows),
    )


def _windows_for_text(
    text: str,
    spans: tuple[tuple[int, int], ...],
    tokenizer: Tokenizer,
    budget: int,
) -> list[tuple[str, tuple[tuple[int, int], ...]]]:
    if len(spans) != 1:
        sentences = [(0, len(text))]
        source_start = 0
    else:
        sentences = _sentence_spans(text)
        source_start = spans[0][0]
    if not sentences:
        sentences = [(0, len(text))]
    windows: list[tuple[str, tuple[tuple[int, int], ...]]] = []
    current_start: int | None = None
    current_end: int | None = None
    for sent_start, sent_end in sentences:
        sentence = text[sent_start:sent_end]
        if tokenizer.count(sentence) > budget:
            if current_start is not None and current_end is not None:
                windows.append(_window_piece(text, current_start, current_end, source_start))
                current_start = None
                current_end = None
            local = 0
            for slice_start, slice_end in _token_slices(sentence, tokenizer, budget):
                windows.append(
                    _window_piece(text, sent_start + slice_start, sent_start + slice_end, source_start)
                )
                local = slice_end
            if local != len(sentence):
                raise ChunkOverflow("rerank windows dropped part of a sentence")
            continue
        if current_start is None:
            current_start, current_end = sent_start, sent_end
            continue
        joined = text[current_start:sent_end]
        if tokenizer.count(joined) <= budget:
            current_end = sent_end
        else:
            windows.append(_window_piece(text, current_start, current_end, source_start))
            current_start, current_end = sent_start, sent_end
    if current_start is not None and current_end is not None:
        windows.append(_window_piece(text, current_start, current_end, source_start))
    if not windows:
        raise ChunkOverflow("rerank windowing produced no text")
    return windows


def _window_piece(
    text: str, start: int, end: int, source_start: int
) -> tuple[str, tuple[tuple[int, int], ...]]:
    return text[start:end], ((source_start + start, source_start + end),)


def _token_slices(text: str, tokenizer: Tokenizer, max_tokens: int) -> list[tuple[int, int]]:
    slices: list[tuple[int, int]] = []
    start = 0
    length = len(text)
    while start < length:
        if tokenizer.count(text[start : start + 1]) > max_tokens:
            raise ChunkOverflow("one character exceeds the hard token limit")
        best = start + 1
        lo = start + 1
        hi = length
        while lo <= hi:
            mid = (lo + hi) // 2
            if tokenizer.count(text[start:mid]) <= max_tokens:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best < length and not text[best - 1].isspace():
            previous_space = text.rfind(" ", start, best)
            if previous_space > start and tokenizer.count(text[start:previous_space]) >= 1:
                best = previous_space
        if best <= start:
            raise ChunkOverflow("could not advance through an over-limit span")
        slices.append((start, best))
        start = best
        while start < length and text[start].isspace():
            start += 1
    return slices
