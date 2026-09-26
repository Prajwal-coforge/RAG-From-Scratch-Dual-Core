# Milestone 3 evidence: ingestion and basic RAG

Recorded 2026-09-25 by `scripts/record-m3-evidence.sh` from clean commit `bd1c0a4fad9ccf249de3a86e80b213c69c0b1a16`. The script refuses to run from a dirty tree. Everything below is from [`2026-09-25T152427Z-terminal.txt`](2026-09-25T152427Z-terminal.txt), with JSON reports beside it.

Runtime: `google/embeddinggemma-300m` at revision `57c266a740f537b4dc058e1b0cda161fd15afa75` through sentence-transformers 6.1.0, Memgraph 3.13.0, and `qwen3:8b` (blob `sha256:a3de86cd1c13…`) through Ollama with thinking off, temperature 0, and seed 7.

## Two-text proof with the new embedder

Task 3.4 required repeating the milestone 1 proof with sentence-transformers before full ingestion. The run starts with `index reset --yes`, which leaves `chunk_embedding` empty, then runs `policy-rag smoke`. Both questions returned their expected text first. The scores were 0.6243 against 0.1265 and 0.5521 against 0.2037, matching the Ollama run in `docs/evidence/m1/` to three decimal places. The production index was size 0 before and after. The report is in [`2026-09-25T152427Z-two-text-smoke.json`](2026-09-25T152427Z-two-text-smoke.json).

## Ingestion

`policy-rag ingest --snapshot <id>` does the following, in order:

1. Loads the manifest and checks every file hash.
2. Runs the quality checks in `backend/app/sources.py`.
3. Parses and chunks with the pinned Hugging Face tokenizer.
4. Checks that every non-space character of every section is inside a chunk span.
5. Checks every embedding input against the 2,048-token limit before encoding.
6. Writes a new index generation to Memgraph.
7. Verifies the generation, then moves the snapshot's publication pointer in one transaction.

Verification checks node counts, vector index growth, stored-vector read-back, and that each chunk is its own nearest neighbour.

| Snapshot | Generation | Documents | Sections | Chunks | Index size | Result |
| --- | --- | ---: | ---: | ---: | --- | --- |
| clean | `gen-3f19662fa38e2eef` | 3 | 21 | 18 | 0 → 18 | published |
| clean (again) | same | | | | | unchanged, nothing written |
| duplicate | `gen-f47ae6fde192fb67` | 4 | 28 | 24 | 18 → 42 | published |
| historical | `gen-969426f1fd3a1262` | 4 | 28 | 24 | 42 → 66 | published |
| imported:skywings-baggage | `gen-ab2b8d1d461c530f` | 1 | 16 | 16 | 66 → 82 | published, 2 warnings |
| imported:aethersky-compensation | `gen-f9683437166aedf9` | 1 | 11 | 10 | 82 → 92 | published, 1 warning |
| imported:synthetic-emissions | `gen-6b929fe8c80e702a` | 1 | 9 | 9 | 92 → 101 | published |
| dirty-stale, ordinary profile | | | | | | refused, exit 3 |
| dirty-stale, evaluation profile | `gen-0d851c0e480a7263` | 3 | 21 | 18 | 101 → 119 | published with recorded reason |

Every generation read back its vectors with drift 0.0, and every chunk matched itself with similarity 1.000000. The largest generated-policy chunk is 133 tokens. Title-only sections have no body and no chunk, which is why 21 sections give 18 chunks.

The generation ID is a hash of these inputs: the manifest, the document hashes, the chunker configuration and tokenizer, the embedder identity, the input-format version, and the profile. Re-ingesting unchanged input is a no-op. Changing any of them builds a new generation next to the old one.

The quality findings in the log are real, not staged:

- `clean` warns that AP-BAG-001 v2 supersedes v1, which that snapshot leaves out on purpose.
- SkyWings warns about its reference to a "SkyWings Airlines Dangerous Goods Policy" that is not in the corpus, and that it has no effective dates.
- `dirty-stale` is blocked as an evaluation-only fixture. Its corrupted metadata (v1 marked active with no end date) passes the metadata checks, because the defect is that v2 is missing from the delivery.

The embedding step reports that its vectors came from the cache. The SQLite cache in `.local/state.sqlite` holds vectors from earlier ingests today by the same pinned model and revision. `index reset` clears Memgraph, not the cache. The cache key is the SHA-256 of the exact embedding input plus model, revision, and dimensions.

## Basic RAG

`policy-rag ask` embeds the question with the query format and searches `chunk_embedding` through `vector_search.search`. The index holds every generation, so k is the whole index size and results are filtered to the published generation. The stored vectors are also scored with exact cosine; in every run the top five agreed and the largest score gap was below 1e-7. Eligible passages go to `qwen3:8b` as numbered evidence. Every cited number is checked against the passages supplied, and every citation is resolved back to character offsets in the source file.

| Question | Snapshot | Top passage | Answer | Status |
| --- | --- | --- | --- | --- |
| Leaking bag: who and how quickly? | clean | AP-BAG-001 v2 §4, 0.7805 | Baggage Duty Supervisor within 10 minutes [1] | answered |
| same | duplicate | AP-BAG-001 v2 §4 (6 v1 chunks excluded as superseded) | 10 minutes [1] | answered |
| same | dirty-stale | AP-BAG-001 v1 §4, 0.7831 | 30 minutes [1] | answered, wrong for 2025-08-01 |
| Rule in force March 2025 | historical, `--as-of 2025-03-15 --include-history` | AP-BAG-001 v1 §4 (v2 excluded as not yet effective) | 30 minutes [1] | answered |
| Exact first-officer hourly base rate | imported:aethersky-compensation | AetherSky §2.1 Base Pay | says the rate is not given | insufficient_evidence |
| Maximum checked-bag weight | imported:skywings-baggage | SkyWings §4 | 32 kg (70 lbs) [1][3] | answered |

The dirty-stale row is the stale-source failure the diagnosis needs. The model answered correctly from what it was given; the source delivery carried the obsolete rule. It is recorded here as observed. The full diagnosis (lab part 8) is milestone 6 work, and this row is not a claim that part is done.

The SkyWings answer collapses two rules into one: Economy allows 23 kg, and no piece may exceed 32 kg. It is cited and resolvable, but whether it counts as correct is a matter for the milestone 4 fact checks.

The answer JSON files ([clean](2026-09-25T152427Z-ask-clean.json), [dirty-stale](2026-09-25T152427Z-ask-dirty-stale.json), [missing rate](2026-09-25T152427Z-ask-missing-rate.json)) hold the retrieval trace, the exact prompt settings, the raw model reply, claims, and resolved citations. The clean answer used 829 evidence tokens against a budget of 3,500; Ollama reported 1,063 prompt tokens.

## Tests

The last two steps of the run executed the test suites:

- `pytest -q`: 92 unit tests passed.
- `pytest -q -m live`: 11 live tests passed.

The live tests in `backend/tests/test_live_rag.py` cover the following:

- re-ingest is a no-op
- a failure injected after writing leaves the old pointer and generation serving, and the failed generation keeps no chunks
- publish, then roll back
- the stale fixture is refused without the evaluation profile
- vector retrieval agrees with exact cosine
- superseded versions are excluded unless history is asked for
- a cited answer resolves to its source
- the missing base rate is reported, not invented

That publish-and-rollback test leaves one extra `previous` generation for `clean`, which the final `index status` shows.

Retirement was tested afterwards, at commit `d140244`, in [`2026-09-25T152759Z-retirement-terminal.txt`](2026-09-25T152759Z-retirement-terminal.txt). The test publishes three generations of `clean` in turn. The third publication retired the oldest: its record stays with status `retired` and 0 of 18 chunks, and the vector index shrank by exactly those 18. All nine live RAG tests passed in that run. A document dropped from a manifest is retired the same way, with the generation that contained it.

The unit tests cover the source-coverage check, over-limit refusal before encoding, query refusal when the embedder differs from the one the index was built with, missing version or hash, hash mismatch, conflicting active versions, bad dates, unresolved references, invented or missing citations, and the evidence budget.

## Limits

- Vector mode only. BM25, fusion, reranking, graph expansion, and the evaluation harness are milestone 4 and later.
- The answer checks prove citations are real and resolvable, not that each claim is entailed by its passage.
- Imported corpora have no authoritative effective dates. Their `as_of` is the ingest date, and the unknown dates are reported as a warning.
- The evidence budget is counted with the EmbeddingGemma tokenizer, not qwen3's, so it is an estimate. The actual prompt token count from Ollama is recorded next to it.
