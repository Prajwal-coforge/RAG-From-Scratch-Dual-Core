"""Token counting is injected. Tests must not pretend to be EmbeddingGemma."""

from __future__ import annotations

import re
from typing import Protocol

TOKEN = re.compile(r"\S+")


class Tokenizer(Protocol):
    name: str

    def count(self, text: str) -> int:
        """Return the token count of an exact string."""


class WordTokenizer:
    """One whitespace-separated word is one token. Test double only."""

    name = "word-v1"

    def count(self, text: str) -> int:
        if not text or not text.strip():
            return 0
        return len(TOKEN.findall(text))
