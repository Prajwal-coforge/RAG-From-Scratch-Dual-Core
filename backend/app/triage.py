"""Deterministic policy triage, before and after retrieval. No model is used.

Before retrieval, triage picks the corpus context, the route, and the mode:

corpus   A policy identifier or issuer name in the question decides it. If
         none is named, a corpus is chosen only when the question has at
         least two words found in that corpus alone, and at least twice as
         many as any other corpus. Otherwise the user is asked which context
         they mean; issuers are never blended. A context the caller selected
         is kept unless the question names, or clearly belongs to, another.
route    cross_policy when the question names two or more policies of the
         chosen corpus, by identifier or by words unique to one policy
         title, or asks about "policies"; it runs graph_rerank. Otherwise
         direct_lookup, which runs hybrid_rerank.

After retrieval, when the top section's rule differs by a reviewed
applicability fact (data/graph/applicability.json) and the question gives
no value for it, the status is needs_clarification and nothing is generated.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from app.chunking.parse import parse_sections
from app.graph import section_number
from app.sources import POLICY_ID_REF, ROOT, available_snapshots, load_snapshot

APPLICABILITY = ROOT / "data" / "graph" / "applicability.json"
GENERATED_CONTEXT = "clean"
MIN_DISTINCTIVE = 2
DOMINANCE = 2.0
STOPWORDS = frozenset(
    """
    about above after again against all also and any are because been before being below between both but can cannot
    could did does doing done down during each else ever every few for from further had has have having her here hers
    how into its itself just may might more most must not now off once only other our out over own per same shall
    she should since some such than that the their them then there these they this those through too under until upon
    very was were what when where which while who whom whose why will with within without would you your yes
    complete exact give tell list say says said happen happens applies apply give get gets make made need needs
    """.split()
)


def terms(text: str) -> set[str]:
    out = set()
    for word in re.findall(r"[a-z][a-z-]*[a-z]", text.lower()):
        if len(word) < 3 or word in STOPWORDS:
            continue
        if word.endswith("s") and len(word) > 4 and not word.endswith("ss"):
            word = word[:-1]
        out.add(word)
    return out


def _alias(issuer: str) -> str:
    [alias] = terms(re.sub(r"[^a-z]", "", issuer.split()[0].lower()))
    return alias


@lru_cache(maxsize=1)
def contexts() -> tuple[dict, ...]:
    """One context per corpus: the snapshot that serves it, its issuer, policies, and vocabulary."""
    found = []
    for snapshot_id in [GENERATED_CONTEXT, *(s for s in available_snapshots() if s.startswith("imported:"))]:
        snapshot = load_snapshot(snapshot_id)
        docs = snapshot.documents
        found.append({
            "corpus_id": snapshot.corpus_id,
            "snapshot_id": snapshot_id,
            "issuer": docs[0].policy_issuer,
            "alias": _alias(docs[0].policy_issuer),
            "policies": {d.policy_id: d.title for d in docs},
            "vocabulary": frozenset().union(*(terms(f"{d.title} {d.text}") for d in docs)),
        })
    return tuple(found)


def _title_words(ctx: dict) -> dict[str, set[str]]:
    words = {pid: terms(title) for pid, title in ctx["policies"].items()}
    return {pid: {w for w in ws if all(w not in other for p, other in words.items() if p != pid)} for pid, ws in words.items()}


def triage(question: str, selected: str | None = None) -> dict:
    """Decide corpus, route, and mode for a question. selected is a corpus_id the caller chose, if any."""
    ctxs = {c["corpus_id"]: c for c in contexts()}
    if selected is not None and selected not in ctxs:
        raise ValueError(f"unknown corpus {selected!r}; choose from {sorted(ctxs)}")
    words = terms(question)
    policy_ids = sorted({m.group(1) for m in POLICY_ID_REF.finditer(question)})
    named = {cid for cid, c in ctxs.items() if c["alias"] in words}
    named |= {cid for cid, c in ctxs.items() for pid in policy_ids if pid in c["policies"]}
    distinctive = {
        cid: sorted(w for w in words if w in c["vocabulary"] and all(w not in o["vocabulary"] for o_id, o in ctxs.items() if o_id != cid))
        for cid, c in ctxs.items()
    }
    ranked = sorted(ctxs, key=lambda cid: (-len(distinctive[cid]), cid))
    best, runner_up = len(distinctive[ranked[0]]), len(distinctive[ranked[1]])
    confident = ranked[0] if best >= MIN_DISTINCTIVE and best >= DOMINANCE * runner_up else None
    signals = {"policy_ids": policy_ids, "named_contexts": sorted(named), "distinctive_terms": {k: v for k, v in distinctive.items() if v},
               "confident_context": confident, "selected": selected}

    chosen, basis, problem = None, None, None
    if len(named) > 1:
        problem = f"the question names more than one issuer ({', '.join(ctxs[c]['issuer'] for c in sorted(named))})"
    elif selected is not None:
        other = next(iter(named)) if named else (confident if confident != selected and not distinctive[selected] else None)
        if other and other != selected:
            problem = f"the selected context is {ctxs[selected]['issuer']}, but the question is about {ctxs[other]['issuer']}"
        else:
            chosen, basis = selected, "selected by the caller"
    elif named:
        chosen = next(iter(named))
        basis = "named in the question"
    elif confident:
        chosen, basis = confident, f"{best} terms found only in this corpus: {', '.join(distinctive[confident])}"
    else:
        problem = "the question does not identify a policy issuer"

    if problem:
        options = sorted(named) if len(named) > 1 else list(ctxs)
        return {
            "status": "needs_clarification",
            "route": "clarify",
            "reason": problem,
            "follow_up_questions": ["Which policy context do you mean: " + "; ".join(
                f"{ctxs[c]['issuer']} ({ctxs[c]['snapshot_id']})" for c in options) + "?"],
            "options": [{"corpus_id": c, "snapshot_id": ctxs[c]["snapshot_id"], "issuer": ctxs[c]["issuer"]} for c in options],
            "signals": signals,
        }

    ctx = ctxs[chosen]
    by_title = [pid for pid, ws in _title_words(ctx).items() if ws & words]
    policies = sorted({*(p for p in policy_ids if p in ctx["policies"]), *by_title})
    cross = len(policies) >= 2 or "policies" in question.lower()
    return {
        "status": "routed",
        "route": "cross_policy" if cross else "direct_lookup",
        "mode": "graph_rerank" if cross else "hybrid_rerank",
        "corpus_id": chosen,
        "snapshot_id": ctx["snapshot_id"],
        "issuer": ctx["issuer"],
        "basis": basis,
        "policies": policies,
        "follow_up_questions": [],
        "signals": signals,
    }


@lru_cache(maxsize=1)
def applicability_rules() -> dict:
    """The reviewed applicability table, checked against the source sections it names."""
    table = json.loads(APPLICABILITY.read_text())
    ctxs = {c["corpus_id"]: c for c in contexts()}
    for corpus_id, facts in table["corpora"].items():
        if not facts:
            continue
        docs = load_snapshot(ctxs[corpus_id]["snapshot_id"]).documents
        sections = {
            section_number(s.heading): d.text[s.body_start : s.body_end]
            for d in docs
            for s in parse_sections(d.text, document_version_id=d.document_version_id, document_title=d.title)
            if section_number(s.heading)
        }
        for fact in facts:
            for number in fact["sections"]:
                text = sections.get(number)
                missing = [m for m in fact["section_mentions"][number] if text is None or m not in text]
                if missing:
                    raise ValueError(f"{corpus_id} fact {fact['fact']}: section {number} does not mention {missing}")
    return table


def missing_facts(corpus_id: str, question: str, top_hit: dict | None) -> list[dict]:
    """Applicability facts the top section depends on that the question does not state."""
    if top_hit is None:
        return []
    number = section_number(top_hit["heading_path"])
    lowered = question.lower()
    missing = []
    for fact in applicability_rules()["corpora"].get(corpus_id, []):
        if number not in fact["sections"]:
            continue
        if any(alias in lowered for aliases in fact["values"].values() for alias in aliases):
            continue
        missing.append({"fact": fact["fact"], "section": number, "values": sorted(fact["values"]), "follow_up": fact["follow_up"]})
    return missing
