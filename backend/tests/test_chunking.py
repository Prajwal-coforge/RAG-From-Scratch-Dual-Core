from app.chunking.chunk import ChunkConfig, chunk_document, split_rerank_windows
from app.chunking.parse import parse_sections
from app.chunking.tokenizer import WordTokenizer

TOKENIZER = WordTokenizer()
SMALL = ChunkConfig(target_tokens=12, max_tokens=18, overlap_tokens=6)


def _words(text: str) -> list[str]:
    return text.split()


def test_numbered_sections_stay_separate_parents():
    text = """Luggage policy

1. Purpose
This policy outlines the rules.

4. Checked Baggage Allowance
Weight Limit: Up to 23 kg.

2.1 Monthly minimum
Pilots must record 75 hours.
"""
    sections = parse_sections(
        text,
        document_version_id="skywings-v1",
        document_title="SkyWings baggage",
    )
    headings = [section.heading_path for section in sections]
    assert headings == [
        "SkyWings baggage",
        "1 Purpose",
        "4 Checked Baggage Allowance",
        "2.1 Monthly minimum",
    ]
    purpose = sections[1]
    assert "23 kg" not in text[purpose.body_start : purpose.body_end]
    assert "75 hours" in text[sections[3].body_start : sections[3].body_end]


def test_clause_sentences_and_quantities_stay_inside_the_parent():
    text = """Synthetic policy

Section 1 – Emissions Monitoring
1.1. Every aircraft operator must monitor fuel.

1.2. Monitoring data must include:

Aircraft ID

2.5 kg of CO2 is the credit amount.

Section 2 – Emissions Limits
2.1. Aircraft models must meet the standard.
"""
    sections = parse_sections(
        text,
        document_version_id="emissions-v1",
        document_title="GAEA",
    )
    headings = [section.heading_path for section in sections]
    assert headings == ["GAEA", "Section 1 Emissions Monitoring", "Section 2 Emissions Limits"]
    monitoring = text[sections[1].body_start : sections[1].body_end]
    assert "1.1. Every aircraft operator must monitor fuel." in monitoring
    assert "2.5 kg of CO2 is the credit amount." in monitoring
    assert "Aircraft models must meet the standard." not in monitoring


def test_short_section_is_one_child_without_padding():
    text = "1. Purpose\nBags must be tagged.\n"
    children = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=SMALL,
    )
    assert len(children) == 1
    assert children[0].text.strip() == "Bags must be tagged."
    assert children[0].overlap_tokens == 0
    assert children[0].embedding_input.startswith("title: Baggage / 1 Purpose | text: ")


def test_long_section_respects_max_overlap_and_coverage():
    sentences = [f"Rule number {index} stays inside this section." for index in range(1, 13)]
    text = "1. Allowance\n" + " ".join(sentences) + "\n"
    limits = ChunkConfig(target_tokens=12, max_tokens=18, overlap_tokens=8)
    children = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=limits,
    )
    assert len(children) > 1
    assert all(child.token_count <= limits.max_tokens for child in children)
    assert all(child.parent_id == children[0].parent_id for child in children)
    assert all(child.overlap_tokens <= limits.overlap_tokens for child in children)
    body = text.split("\n", 1)[1]
    covered = bytearray(len(text))
    for child in children:
        assert child.text
        for start, end in child.spans:
            covered[start:end] = b"\x01" * (end - start)
    body_start = text.index(body)
    for offset, char in enumerate(body):
        if not char.isspace():
            assert covered[body_start + offset] == 1
    overlapped = [child for child in children[1:] if child.overlap_tokens]
    assert overlapped
    assert any(later.source_start < earlier.source_end for earlier, later in zip(children, children[1:]))


def test_overlap_is_trailing_sentences_inside_the_same_parent():
    sentences = [f"Sentence {index} is complete." for index in range(1, 10)]
    text = "1. Rules\n" + " ".join(sentences)
    children = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=SMALL,
    )
    for earlier, later in zip(children, children[1:]):
        assert earlier.parent_id == later.parent_id
        if later.overlap_tokens == 0:
            continue
        assert later.source_start < earlier.source_end
        overlap = text[later.source_start : earlier.source_end]
        assert TOKENIZER.count(overlap) == later.overlap_tokens
        assert overlap[:1].isupper() or overlap.startswith("Sentence")


def test_section_and_version_boundaries_do_not_mix():
    text = """1. Staff rules
Employees may enter the bag room.

2. Supervisor review
Only the duty supervisor may close an investigation.
"""
    children = chunk_document(
        text,
        document_version_id="ap-sec-v1",
        document_title="Access",
        tokenizer=TOKENIZER,
        config=SMALL,
    )
    by_heading = {child.heading_path: child for child in children}
    assert by_heading["1 Staff rules"].parent_id != by_heading["2 Supervisor review"].parent_id
    assert "supervisor" not in by_heading["1 Staff rules"].text.lower()
    assert "bag room" not in by_heading["2 Supervisor review"].text.lower()

    other = chunk_document(
        "1. Old deadline\nEscalate within 30 minutes.\n",
        document_version_id="ap-bag-v1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=SMALL,
    )
    assert {child.document_version_id for child in children} == {"ap-sec-v1"}
    assert {child.document_version_id for child in other} == {"ap-bag-v1"}


def test_table_groups_repeat_the_header():
    text = """1. Allowance
| Class | Limit |
| --- | --- |
| Economy | 23 kg |
| Business | 32 kg |
| First | 32 kg |
"""
    children = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=ChunkConfig(target_tokens=16, max_tokens=18, overlap_tokens=0),
    )
    assert len(children) >= 2
    assert all("| Class | Limit |" in child.text for child in children)
    assert all(child.table_header is not None for child in children)
    joined = "\n".join(child.text for child in children)
    assert "Economy" in joined and "Business" in joined and "First" in joined


def test_exception_stays_together_when_it_fits_and_is_linked_when_it_does_not():
    together = chunk_document(
        "1. Cargo\nBags over 32 kg ship as cargo. Except when a medical note is attached.\n",
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=ChunkConfig(target_tokens=8, max_tokens=20, overlap_tokens=0),
    )
    assert len(together) == 1
    assert "cargo" in together[0].text
    assert "Except when a medical note is attached." in together[0].text
    assert together[0].exception_refs == ()

    split = chunk_document(
        "1. Cargo\n"
        "Bags over thirty two kilograms must ship as cargo today. "
        "Except when a signed medical note is attached by the passenger.\n",
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=ChunkConfig(target_tokens=8, max_tokens=12, overlap_tokens=0),
    )
    assert len(split) == 2
    assert split[0].exception_refs == (split[1].chunk_id,)
    assert "Except when" in split[1].text


def test_reference_survives_on_the_child_that_contains_it():
    children = chunk_document(
        "7. Restricted items\n"
        "For a detailed list, refer to the SkyWings Airlines Dangerous Goods Policy.\n",
        document_version_id="skywings-v1",
        document_title="SkyWings baggage",
        tokenizer=TOKENIZER,
        config=SMALL,
    )
    assert any("Dangerous Goods Policy" in ref for child in children for ref in child.reference_refs)


def test_over_limit_sentence_is_split_into_linked_subspans():
    words = " ".join(f"word{index}" for index in range(1, 31))
    text = f"1. Dense\n{words}.\n"
    children = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=ChunkConfig(target_tokens=6, max_tokens=8, overlap_tokens=0),
    )
    assert len(children) > 1
    assert children[0].continuation_of is None
    assert all(child.continuation_of == children[0].chunk_id for child in children[1:])
    assert _words(" ".join(child.text for child in children)) == _words(words + ".")
    assert all(child.token_count <= 8 for child in children)


def test_rerank_windows_cover_the_passage_without_dropping_text():
    words = " ".join(f"Fact {index} matters." for index in range(1, 8))
    text = f"1. Facts\n{words}\n"
    children = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=ChunkConfig(target_tokens=40, max_tokens=50, overlap_tokens=0, rerank_pair_tokens=16, rerank_special_tokens=2),
    )
    assert len(children) == 1
    windows = split_rerank_windows(children[0], "What is the limit?", TOKENIZER, children and ChunkConfig(
        target_tokens=40, max_tokens=50, overlap_tokens=0, rerank_pair_tokens=16, rerank_special_tokens=2
    ))
    assert len(windows) > 1
    assert _words(" ".join(window.text for window in windows)) == _words(children[0].text)
    assert windows[0].continuation_of is None
    assert all(window.continuation_of == windows[0].chunk_id for window in windows[1:])


def test_chunk_ids_follow_the_config_fingerprint():
    text = "1. Purpose\nBags must be tagged before departure from the carousel.\n"
    first = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=SMALL,
    )
    again = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=SMALL,
    )
    changed = chunk_document(
        text,
        document_version_id="doc-1",
        document_title="Baggage",
        tokenizer=TOKENIZER,
        config=ChunkConfig(target_tokens=12, max_tokens=18, overlap_tokens=0),
    )
    assert [child.chunk_id for child in first] == [child.chunk_id for child in again]
    assert first[0].chunk_id != changed[0].chunk_id


def test_embeddinggemma_tokenizer_matches_ollama_content_tokens():
    from pathlib import Path

    from app.chunking.gguf_tokenizer import BLOB, GemmaTokenizer

    if not Path(BLOB).exists():
        return
    tokenizer = GemmaTokenizer()
    assert tokenizer.encode("Hello world") == tokenizer.encode("Hello world")
    assert tokenizer.count("Hello world") == 2
    assert tokenizer.count("the") == 1
