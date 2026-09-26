# Milestone 2 evidence: sources, generated policies, and fixtures

Recorded 2026-09-25. Chat model `qwen3:8b`, blob `sha256:a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`, Ollama 0.34.0, thinking off. Every run below started from a clean commit, printed in the first line of its terminal log.

## Generated documents

| Document | Status | Effective | Prose words | References | Review edits |
| --- | --- | --- | ---: | --- | ---: |
| `AP-BAG-001-v2.md` | active | from 2025-07-01 | 611 | AP-INC-002, AP-SEC-003 | 0 |
| `AP-INC-002-v1.md` | active | from 2025-01-01 | 615 | AP-BAG-001, AP-SEC-003 | 1 |
| `AP-SEC-003-v1.md` | active | from 2025-01-01 | 599 | AP-BAG-001, AP-INC-002 | 1 |
| `AP-BAG-001-v1.md` | superseded | 2025-01-01 to 2025-06-30 | 599 | AP-INC-002, AP-SEC-003 | 0 |

The files are in `data/sources/generated/`. Word counts exclude headings, and `wc -w` gives the same numbers. The four accepted drafts all come from run `2026-09-25T143259Z`, attempt 2.

Section 4 of both AP-BAG-001 versions opens with the same sentence, apart from the deadline:

> When a baggage handler finds a damaged, leaking, or unattended checked bag in the baggage make-up area, the handler must escalate the incident to the Baggage Duty Supervisor within **10** (v2) / **30** (v1) minutes of discovery and must report it under AP-INC-002.

Neither version uses "immediately", "promptly", "as soon as", or "without delay", so no competing timing rule exists. AP-INC-002 section 3 sends baggage incidents to "AP-BAG-001 section 4". AP-SEC-003 names the Requesting Staff Member, Line Manager, and Security Duty Manager as steps in the approval procedure, not as readers.

The dates and versions are fixture choices. They live in `data/sources/generated/catalog.json`, not in the document text.

## How a draft is accepted

`policy-rag corpus generate` sends the prompt in `backend/app/corpus/generate.py` with the brief and required sentences from `backend/app/corpus/policies.py`. `backend/app/corpus/validate.py` checks each draft for the following:

- the exact title line and the six numbered section headings in order
- 550 to 750 prose words, which keeps a margin inside the required 500 to 800
- the required sentence, word for word, in its named section
- the required policy references, and no invented policy IDs
- no forbidden phrases, no lists or tables, and no dates or version numbers

A rejected draft goes back to the model with the failed checks and the number of words to add or cut. If a revision repeats the draft word for word, the next attempt starts fresh.

Each attempt is saved under `data/sources/generated/runs/<run>/<key>/attempt-<n>/`:

- `request.json`: the exact request
- `response.json`: the raw Ollama response, with timings and token counts
- `raw.md`: the draft text
- `checks.json`: the check results

`run.json` in each run folder records the commit, the model digest, and every attempt.

`policy-rag corpus review` applies `data/sources/generated/review-edits.json` to the accepted raw drafts. Each edit is pinned to the draft's hash, must match exactly once, and the edited text must still pass every check. The raw drafts are not modified. There are two edits:

- AP-INC-002: removed "immediately" from "must be reported immediately by the affected staff member". That sentence sits in the paragraph that defers to the AP-BAG-001 section 4 deadline. Run `143810Z` tried to regenerate AP-INC-002 without vague timing words six times, and every draft still had one.
- AP-SEC-003: "air,side" to "airside", a typo.

## All runs, including rejected ones

| Run | Commit | Outcome |
| --- | --- | --- |
| `140142Z` | `50638d8` | All four passed the first checks. Rejected on reading: the deadline sentence was in section 3, section 4 said "immediately", and one draft had exactly 500 words. The checks were tightened. |
| `140544Z` | `b4dce26` | AP-INC-002 overshot to 900–1,420 words in six attempts. Nothing written. |
| `141332Z` | `ce442d1` | AP-SEC-003 stayed at 428–549 words. Nothing written. |
| `142007Z` | `d98d67d` | Revision feedback added. AP-SEC-003 returned the same 548-word draft six times. Nothing written. |
| `142621Z` | `2f66030` | All four passed. Rejected on reading: v1 said "reported immediately" and "promptly" outside section 4, and AP-SEC-003 had a typo. |
| `143259Z` | `622092f` | All four passed. These are the accepted drafts. |
| `143810Z` | `91f0207` | Tried to regenerate AP-INC-002 with vague timing banned. It failed six times, so the single-word review edit was used instead. |

The terminal output of each run is saved in this folder as `<run>-generate-terminal.txt`.

## Manifests

`policy-rag corpus manifests` builds these from the catalog. They are write-once, and `SHA256SUMS.json` records their hashes.

| Manifest | Contents |
| --- | --- |
| `data/manifests/clean.json` | AP-BAG-001 v2, AP-INC-002 v1, and AP-SEC-003 v1 |
| `data/manifests/duplicate.json` | Clean plus AP-BAG-001 v1, correctly marked superseded |
| `data/manifests/dirty-stale.json` | AP-BAG-001 v1 supplied as active, AP-INC-002 v1, and AP-SEC-003 v1. v2 is missing. |
| `data/manifests/historical.json` | All four versions with correct dates |

The dirty-stale corruption is recorded in the manifest's `fixture` block:

- the field changes: `publication_status` goes from superseded to active, and `effective_to` goes from 2025-06-30 to null
- the missing v2, and the original v1 metadata
- `content_altered: false`

The v1 file is byte-identical across the duplicate, dirty-stale, and historical manifests. The manifest builder refuses two active versions of one policy and any file whose hash does not match. The dirty-stale fixture passes those checks on purpose: the defect is a stale delivery, not a malformed one.

## Imported sources

`policy-rag corpus import` verified all three pinned files against `airport-policy-rag-spec/config/corpus-manifest.json` and kept the Apache-2.0 `LICENSE`. A file whose hash does not match is refused and never written to disk.

## Chunking check

With the EmbeddingGemma tokenizer, each generated document parses into its six numbered sections, one child per section, with a largest child of 142 tokens. The parser change that made this work is that `## 1. Purpose and Scope` is now treated as a numbered heading.

## Tests

`uv run pytest`: 59 passed, 1 live test deselected. `backend/tests/test_corpus.py` covers the draft checks, the prompt and revision feedback, checksum refusal, the manifest contents, the dirty-stale corruption record, the write-once manifests, and the review edits. It also rebuilds the committed manifests and re-checks the committed documents against their raw drafts.
