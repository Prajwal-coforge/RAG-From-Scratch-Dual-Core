from pathlib import Path

import pytest

from policy_rag.config import POLICIES_DIR
from policy_rag.chunking import chunk_document
from policy_rag.extract import load_policies

pytestmark = pytest.mark.skipif(
    not POLICIES_DIR.exists() or not list(POLICIES_DIR.glob("*.pdf")),
    reason="policies/ PDFs are not present",
)


def test_extract_and_chunk_real_pdfs():
    docs = load_policies(POLICIES_DIR)
    assert len(docs) >= 1
    total = 0
    names = {doc["name"] for doc in docs}
    for doc in docs:
        assert doc["text"].strip()
        assert len(doc["text"]) > 500, f"{doc['name']} too short after clean"
        chunks = chunk_document(doc["text"], name=doc["name"], version=doc["version"])
        assert chunks, f"no chunks for {doc['name']}"
        total += len(chunks)
        assert all(c.section for c in chunks)
    assert total >= 4
    if len(docs) >= 4:
        assert any("Whistleblower" in n for n in names)
