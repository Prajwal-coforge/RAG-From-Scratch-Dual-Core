# Milestone 4 evidence: hybrid retrieval, reranking, and evaluation

Recorded with `scripts/record-m4-evidence.sh dev` from commit `0a7a7bb` and
`scripts/record-m4-evidence.sh heldout` from commit `90a4b12`. The script
refuses to run from a dirty tree.

## Files

| File | What it is |
| --- | --- |
| `2026-09-25T160436Z-dev-terminal.txt` | Terminal log of the dev run |
| `2026-09-25T160436Z-demo-<mode>.json` | `ask` report for the hybrid demonstration in each mode |
| `2026-09-25T160436Z-dev-evaluation.json` | Dev suite report: configuration, per-mode summary, per-case outcomes, judge output, needle check |
| `2026-09-25T161343Z-heldout-terminal.txt` | Terminal log of the held-out run and the live tests |
| `2026-09-25T161343Z-heldout-evaluation.json` | Held-out suite report |

The held-out labels were drafted by the coding agent and machine-checked
against the sources; they were not reviewed by the project owner before this
run. The owner chose to run first and disclose it (`FREEZE.json`,
`review_status`). The freeze hashes matched at run time.

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

## Held-out suite results (12 cases: 9 generated, 3 imported)

Run once, after dev tuning ended, with no changes afterwards.

| Mode | recall@3 | recall@5 | fact accuracy | case pass rate | citation validity | judge support | p50 / p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vector | 1.00 | 1.00 | 0.97 | 0.92 | 1.00 | 0.93 | 3135 / 4833 |
| keyword | 1.00 | 1.00 | 0.97 | 0.92 | 1.00 | 1.00 | 2612 / 4760 |
| hybrid | 1.00 | 1.00 | 0.97 | 0.92 | 1.00 | 1.00 | 2638 / 6084 |
| hybrid_rerank | 1.00 | 1.00 | 0.97 | 0.92 | 1.00 | 0.92 | 2290 / 4381 |

The release targets (candidate recall ≥ 0.90, recall@5 ≥ 0.85, fact accuracy
≥ 0.85, citation validity 100%) are met in every mode. The modes do not
separate on this suite: its questions carry topic words, and the eligible
pool averages 16.4 chunks.

- H-G03 fails in every mode. AP-BAG-001 section 5 states two requirements
  for the bag: it "must not be handled further until it is approved or
  removed", and it "must be isolated and secured". Every answer gives the
  second and omits the first, which is the only one the label requires. The
  two policy references are correct and both labelled clauses are retrieved.
  The answer is incomplete against a label that is narrower than the
  question; the label is part of the pending owner review.
- H-G08, hybrid_rerank: the judge marked the correct "30 minutes" answer
  unsupported because the passage does not literally say "March 2025". This
  is a judge false negative.

Live tests after the held-out run: 30 passed, 1 failed. The failure is
`test_generated_case_passes[H-G03]`, the same answer error. It has not been
skipped, marked as expected to fail, or fixed by tuning against the held-out case.

## Needle check

`Form QX-7731 ...` planted in an isolated copy of the clean generation
(`:NeedleChunk`, vector index `needle_embedding`, no publication pointer).
Rank 1 in every mode, by code and by paraphrase. Isolation check: no pointer
to the needle generation, production index size unchanged, no needle nodes
left.
