from policy_rag.chunking import chunk_document, split_oversized, split_sections
from policy_rag.retrieve import Hit, rrf_merge

SAMPLE = """
1.0 Context:
The Company requires Directors and Staff Members to observe high standards of ethics.

2.0 Objective:
The purpose of this Policy is to enable a person who observes an unethical practice to approach the Company.

5.0 Definitions:
The definitions of some of the key terms used in this Policy are given below.
(a) “Audit Committee” means the Audit Committee constituted by the Board of the Company;
(b) “Board” means the Company’s board of Directors;
(c) “Staff Member” means every employee of the Company including a trainee;
(i) “Protected Disclosure” means any disclosure made in good faith that discloses unethical activity.
This sentence is extra padding so the definitions section is long enough that the recursive splitter must cut on lettered clauses instead of leaving one oversized blob. Protected Disclosure is the citation unit hybrid retrieval should still label as 5.0 Definitions even after the split. More padding about confidentiality, investigators, good faith, and the code of conduct keeps this block above the size cap.

8.0 Reporting a Concern:
The Company has established dedicated reporting channels. Whistleblowers should use those channels.
"""


def test_split_on_numbered_headings():
    sections = split_sections(SAMPLE)
    numbers = [n for n, _, _ in sections]
    assert numbers == ["1.0", "2.0", "5.0", "8.0"]
    assert "Objective" in sections[1][1]


def test_short_section_stays_one_chunk():
    chunks = chunk_document(SAMPLE, name="Whistleblower Policy", version="1.5")
    objectives = [c for c in chunks if c.section.startswith("2.0")]
    assert len(objectives) == 1
    assert "unethical practice" in objectives[0].text


def test_definitions_keep_section_label_after_split():
    chunks = chunk_document(
        SAMPLE,
        name="Whistleblower Policy",
        version="1.5",
        max_chars=400,
        overlap=80,
    )
    defs = [c for c in chunks if c.section.startswith("5.0")]
    assert len(defs) >= 2
    assert all("5.0 Definitions" == c.section for c in defs)
    assert any("Protected Disclosure" in c.text for c in defs)


def test_recursive_lettered_split():
    body = (
        "(a) first clause about reporting.\n"
        "(b) second clause about confidentiality and protection of identity.\n"
        "(c) third clause about investigators and the audit committee chair."
    )
    parts = split_oversized(body * 8, max_chars=220, overlap=40)
    assert len(parts) > 1


def test_metadata_on_chunks():
    chunks = chunk_document(SAMPLE, name="Whistleblower Policy", version="1.5")
    assert chunks
    assert chunks[0].metadata()["name"] == "Whistleblower Policy"
    assert chunks[0].metadata()["version"] == "1.5"
    assert "section" in chunks[0].metadata()


def test_rrf_prefers_agreement():
    a = Hit("s8", "report", {"section": "8.0"}, 1.0, "vector")
    b = Hit("s2", "objective", {"section": "2.0"}, 0.9, "vector")
    c = Hit("s8", "report", {"section": "8.0"}, 2.0, "keyword")
    merged = rrf_merge([[a, b], [c]])
    assert merged[0].id == "s8"
    assert "keyword" in merged[0].source and "vector" in merged[0].source
