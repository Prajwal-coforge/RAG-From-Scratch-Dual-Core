"""Okapi BM25 keyword retrieval, written here with no search library.

Terms are lowercase. These stay single terms instead of being split:
- policy identifiers such as AP-BAG-001 or SAPCPA-2025
- section references: "section 4", a heading number, and a dotted number
  such as 4.2 all become § terms (§4, §4.2)
- number-unit pairs such as "23 kg" (term 23kg), with unit spellings
  merged ("15 grams" and "15 g" are both 15g), and money such as $3.25

No stopwords are removed, so negations (not, no, never, without) remain
searchable terms.

Exact-match boost: every exact term in the query (identifier, section
reference, number-unit pair, money, or a quoted phrase) that appears in a
chunk adds EXACT_BOOST to that chunk's BM25 score. The BM25 score, the
boost, the matched terms, and the rank are all recorded.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

K1 = 1.5
B = 0.75
EXACT_BOOST = 2.0

UNITS = r"(?:kg|kilograms?|lbs?|pounds?|cm|in|ml|mg|g|grams?|km|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?|%)"
TOKEN = re.compile(
    r"(?P<ident>\b[a-z]{2,}(?:-[a-z]{2,})*-\d{2,}\b)"
    r"|(?P<section>\bsection\s+(?P<secnum>\d+(?:\.\d+)*))"
    r"|(?P<money>\$\s?\d[\d,]*(?:\.\d+)?)"
    r"|(?P<unit>\b\d+(?:[.,]\d+)?\s?" + UNITS + r"(?![a-z]))"
    r"|(?P<dotted>\b\d+(?:\.\d+)+\b)"
    r"|(?P<word>[a-z0-9§]+(?:'[a-z]+)?)"
)
QUOTED = re.compile(r"[\"“]([^\"”]{3,})[\"”]")
HEADING_NUMBER = re.compile(r"^(?:section\s+)?(\d+(?:\.\d+)*)\b", re.IGNORECASE)
EXACT_KINDS = ("ident", "section", "money", "unit", "dotted")


@dataclass(frozen=True)
class Term:
    text: str
    kind: str


UNIT_NAMES = {
    "kilogram": "kg", "kilograms": "kg", "gram": "g", "grams": "g",
    "lbs": "lb", "pound": "lb", "pounds": "lb",
    "minute": "min", "minutes": "min", "mins": "min",
    "hour": "h", "hours": "h", "hr": "h", "hrs": "h",
    "days": "day", "weeks": "week", "months": "month", "years": "year",
}
UNIT_SPLIT = re.compile(r"^(\d+(?:\.\d+)?)([a-z%]+)$")


def _unit_term(value: str) -> str:
    compact = re.sub(r"[\s,]", "", value)
    match = UNIT_SPLIT.match(compact)
    if not match:
        return compact
    number, unit = match.groups()
    return number + UNIT_NAMES.get(unit, unit)


def tokenize(text: str) -> list[Term]:
    terms = []
    for match in TOKEN.finditer(text.lower()):
        kind = match.lastgroup
        if kind == "secnum":
            kind = "section"
        value = match.group(0)
        if kind == "section":
            value = "§" + match.group("secnum")
        elif kind == "dotted":
            value = "§" + value
        elif kind == "unit":
            value = _unit_term(value)
        elif kind == "money":
            value = re.sub(r"[\s,]", "", value)
        terms.append(Term(value, kind))
    return terms


def document_terms(chunk: dict) -> list[str]:
    """Title, heading, and text. The heading number also counts as a section reference."""
    terms = [t.text for t in tokenize(chunk["document_title"])]
    heading = chunk["heading_path"]
    number = HEADING_NUMBER.match(heading.strip())
    if number:
        terms.append("§" + number.group(1))
    terms.extend(t.text for t in tokenize(heading))
    terms.extend(t.text for t in tokenize(chunk["text"]))
    return terms


def exact_terms(query: str) -> list[str]:
    found = [t.text for t in tokenize(query) if t.kind in EXACT_KINDS]
    found.extend(f'"{phrase.lower()}"' for phrase in QUOTED.findall(query))
    return list(dict.fromkeys(found))


class BM25Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.docs = [Counter(document_terms(chunk)) for chunk in chunks]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        self.df: Counter = Counter()
        for doc in self.docs:
            self.df.update(doc.keys())
        self.texts = [
            f"{chunk['document_title']} {chunk['heading_path']} {chunk['text']}".lower() for chunk in chunks
        ]

    def idf(self, term: str) -> float:
        n = len(self.docs)
        df = self.df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _contains(self, index: int, doc: Counter, term: str) -> bool:
        if term.startswith('"'):
            return term[1:-1] in self.texts[index]
        return doc.get(term, 0) > 0

    def search(self, query: str, k: int) -> list[dict]:
        query_terms = [t.text for t in tokenize(query)]
        unique = list(dict.fromkeys(query_terms))
        exact = exact_terms(query)
        results = []
        for index, doc in enumerate(self.docs):
            score = 0.0
            for term in unique:
                tf = doc.get(term, 0)
                if not tf:
                    continue
                norm = K1 * (1 - B + B * self.lengths[index] / self.avg_length)
                score += self.idf(term) * tf * (K1 + 1) / (tf + norm)
            matched = [term for term in exact if self._contains(index, doc, term)]
            boost = EXACT_BOOST * len(matched)
            if score + boost > 0:
                results.append(
                    {
                        "chunk_id": self.chunks[index]["chunk_id"],
                        "bm25": score,
                        "exact_terms": matched,
                        "boost": boost,
                        "score": score + boost,
                    }
                )
        results.sort(key=lambda r: (-r["score"], r["chunk_id"]))
        for rank, result in enumerate(results, start=1):
            result["rank"] = rank
        return results[:k]
