# Milestone 4 evidence: hybrid retrieval, reranking, and evaluation

Recorded with `scripts/record-m4-evidence.sh dev` from commit `0a7a7bb`. The
script refuses to run from a dirty tree.

## Files

| File | What it is |
| --- | --- |
| `2026-09-25T160436Z-dev-terminal.txt` | Full terminal log of the run |
| `2026-09-25T160436Z-demo-<mode>.json` | `ask` report for the hybrid demonstration in each mode |
| `2026-09-25T160436Z-dev-evaluation.json` | Dev suite report: configuration, per-mode summary, per-case outcomes, judge output, needle check |

The held-out suite has not been run yet. It waits for the project owner's
review of the held-out labels (see `data/evaluation/heldout/FREEZE.json`).

## Hybrid demonstration (selected on dev data)

Question: "What does AP-SEC-003 section 2 say?" on the clean snapshot (dev case
D-G07). It was added after the first dev run showed every mode ranking the
labelled clause first on the original twelve dev cases.

| Mode | Rank of section 2 | Status |
| --- | --- | --- |
| vector | not in the top 5 | insufficient_evidence |
| keyword | 1 (BM25 2.53 + boost 4.0 for `ap-sec-003` and `§2`) | answered, citation resolved |
| hybrid | 2 (RRF of vector #7 and keyword #1) | answered, citation resolved |
| hybrid_rerank | 4 (cross-encoder moved it down from #2) | answered, citation resolved |

The question carries only an identifier and a section number, so vector
search has no topic words to match. The cross-encoder also discounts the
identifier; hybrid without reranking ranks this clause higher. This shows one
query where hybrid beats vector; it is not a general claim of superiority.

## Dev suite results (13 cases: 7 generated, 6 imported)

| Mode | recall@3 | recall@5 | fact accuracy | case pass rate | citation validity | judge support | p50 / p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vector | 0.92 | 0.92 | 0.90 | 0.92 | 1.00 | 0.79 | 2568 / 4772 |
| keyword | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.81 | 2794 / 5298 |
| hybrid | 1.00 | 1.00 | 1.00 | 0.92 | 1.00 | 0.93 | 2461 / 3859 |
| hybrid_rerank | 0.92 | 1.00 | 1.00 | 1.00 | 1.00 | 0.92 | 2783 / 5715 |

Candidate recall@20 is 1.00 in every mode, but the mean eligible pool is 15.6
chunks, so a 20-candidate pool contains nearly everything. It says little
here. Latency is measured over 13 runs per mode, which is too few for a
stable p95; it includes generation, not the judge.

Failures and disagreements, from the per-case outcomes:

- D-G07, vector: section 2 not retrieved; the model abstained (status mismatch).
- D-I02, hybrid: the model presented the SkyWings category list as the
  complete dangerous-goods list instead of abstaining.
- D-I01, all modes: the deterministic checks pass (the answer says bags over
  32 kg go as cargo), but the judge marked a claim unsupported: the answer
  also says such a bag "incurs a fee of $75", which the source does not say.
  This is a real unsupported claim that the fact patterns do not cover; it is
  recorded for manual review, not patched into the labels.

The judge is the same `qwen3:8b` model that generated the answers and never
decides pass or fail.

## Tuning done on dev

One prompt change after the first dev run: abstain with the
`INSUFFICIENT_EVIDENCE:` line when the evidence says a value is not stated or
points to a document that was not supplied. Before it, D-I05 (exact base pay)
failed in every mode because the model abstained in prose without the marker.

## Needle check

`Form QX-7731 ...` planted in an isolated copy of the clean generation
(`:NeedleChunk`, vector index `needle_embedding`, no publication pointer).
Rank 1 in every mode, by code and by paraphrase. Isolation check: no pointer
to the needle generation, production index size unchanged, no needle nodes
left.
