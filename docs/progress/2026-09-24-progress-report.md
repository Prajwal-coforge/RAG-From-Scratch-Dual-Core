# Progress report — 2026-09-24

Airport Policy RAG overhaul. This report records what is in the working tree. It is not a claim that the lab is complete, and it is not instructor approval of the stack substitution.

OpenSpec change `build-airport-policy-rag` is proposed only. Tasks 0.1–0.6, 1.1–1.5, 2.1–2.5, and 3.1–3.9 are checked. The other 28 tasks are open. Four rubric rows have recorded evidence: the minimal retrieval proof (7 points), generated documents (8), full ingestion (10), and basic RAG (10). None of it is in a submission PDF yet. The UI has not been started. The change is not archived.

## Decisions

The assignment suggests sentence-transformers and Chroma. Since milestone 3, embeddings use sentence-transformers with `google/embeddinggemma-300m` at a pinned revision, running locally. Memgraph replaces Chroma, and Ollama `qwen3:8b` generates answers. There is no data lake and no hosted model. Details are in `docs/decisions/0001-stack-substitution-and-corpus.md` and `0005-retrieval-and-evaluation-methods.md`.

On 2026-09-25 the data governance layer and local authentication were removed from the handoff and the OpenSpec change. The app serves one local user with no access control. Source lineage, versions, and the stale-source fixtures stay. Details are in `docs/decisions/0004-no-data-governance-layer.md`.

The imported corpus is three aviation files from `DecisionsDev/policy-corpus` at commit `948dacadbe03ca4d978ea3d6ccc19131e6a92efb`. Issuers stay separate. The four generated AeroPolicy documents are in `data/sources/generated/`. The old company-policy PDFs were removed from `policies/`.

## What is done

| Area | State |
| --- | --- |
| Handoff | `airport-policy-rag-spec/` is the specification. Stack and corpus choices are recorded. |
| Preflight | `docs/preflight/2026-09-24-environment.md`. Apple M5, 24 GB RAM, Metal available to Ollama. Doctor passed at 2026-09-24T20:32:08Z, including a Memgraph restart. |
| Ollama | 0.34.0 on `127.0.0.1:11434`. `qwen3:8b` answers questions. `embeddinggemma` served the milestone 1 proof and is kept only to reproduce it. |
| Memgraph | `memgraph/memgraph-mage:3.13.0` via `infra/compose.yaml`, bound to `127.0.0.1:7687`. Lab 3.7.1 is at `http://127.0.0.1:3000`. |
| Graph shape | Unique `id` constraints and the cosine index `chunk_embedding` (768 dimensions). Ingested generations add `IndexGeneration`, `Policy`, `PolicyVersion`, `Section`, and `Chunk` nodes with `HAS_VERSION`, `HAS_SECTION`, `HAS_CHUNK`, and `SUPERSEDES` edges, plus one `Publication` pointer per snapshot. The schema-preview nodes from `infra/schema-preview.cypher` stay for the doctor's persistence check. |
| OpenSpec | CLI 1.13.2 initialized for Cursor. Commands are `.cursor/commands/opsx-*.md`. `openspec validate` passed for `build-airport-policy-rag`. The change is not archived. |
| Chunking | `backend/app/chunking/`. Parent is one section. Child target is 300 EmbeddingGemma tokens, maximum 400, overlap at most 50 whole sentences. Version and section boundaries are not crossed. |
| Two-text proof | `policy-rag smoke` at commit `cbbbd9b`. Two texts embedded by `embeddinggemma`, stored in Memgraph under their own index `smoke_text_embedding`, and each question returned its expected text first (0.6242 vs 0.1266, 0.5523 vs 0.2038). Evidence in `docs/evidence/m1/`. `chunk_embedding` stayed at size 0. |
| Generated policies | `policy-rag corpus generate` at commit `622092f`, run `2026-09-25T143259Z`. AP-BAG-001 v2 (10-minute escalation), AP-INC-002 v1, AP-SEC-003 v1, and the obsolete AP-BAG-001 v1 (30-minute escalation), 599–615 prose words each. Every attempt, including rejected drafts and six earlier runs, is saved with its request and raw response. Two recorded review edits. Evidence in `docs/evidence/m2/`. |
| Manifests | `data/manifests/` clean, duplicate, dirty-stale, and historical, write-once with `SHA256SUMS.json`. The dirty-stale fixture supplies v1 as active and omits v2; the field changes and original metadata are recorded in its `fixture` block. |
| Embedder | `backend/app/embedder.py`. sentence-transformers `google/embeddinggemma-300m` at revision `57c266a7`, loaded from the local cache. Inputs over 2,048 tokens are refused before encoding. The two-text proof was repeated with it and passed (0.6243 vs 0.1265, 0.5521 vs 0.2037). |
| Ingestion | `policy-rag ingest --snapshot <id>` at commit `bd1c0a4`. It validates the snapshot, then chunks and checks that the chunks cover every section. It embeds, writes a new Memgraph generation, verifies it, and publishes it atomically. Re-running unchanged input is a no-op. Rollback keeps one previous generation, and a third publication retires the oldest. Seven snapshots are published: 119 chunks in total, every vector read back exactly. `dirty-stale` publishes only under `--profile evaluation --reason`. Evidence in `docs/evidence/m3/`. |
| Basic RAG | `policy-rag ask` searches the Memgraph vector index, checks the result against exact cosine, answers with `qwen3:8b`, and validates and resolves every citation to file offsets. The clean snapshot answers "Baggage Duty Supervisor within 10 minutes [1]". The stale fixture answers 30 minutes from the obsolete clause. The AetherSky base-rate question returns `insufficient_evidence`. |
| Tests | 92 unit tests pass on Python 3.12.14. `pytest -m live` runs 12 tests against the real embedder, Memgraph, and Ollama; all passed. |
| Imported sources | Three files fetched, SHA-256 checked, Apache-2.0 `LICENSE` kept under `data/sources/imported/`. |

Chunks per imported corpus, from the milestone 3 ingest. Every section was under 400 tokens, so each section with a body is one child.

| Corpus | Sections | Chunks | Largest chunk |
| --- | ---: | ---: | ---: |
| `skywings-baggage` | 16 | 16 | 176 tokens |
| `aethersky-compensation` | 11 | 10 | 150 tokens |
| `synthetic-emissions` | 9 | 9 | 136 tokens |

SkyWings keeps headings such as `4 Checked Baggage Allowance`. AetherSky keeps `2.1 Base Pay`. GAEA keeps `Section 1 Emissions Monitoring` through `Section 8 Definitions`. Clause lines such as `1.1.` and quantities such as `2.5 kg` stay inside the parent.

## What is not done

- Host `npm` is not installed. OpenSpec commands were generated from package 1.13.2 and committed; a global `openspec` binary is not on `PATH`. The React package lock waits until UI work.
- Retrieval is vector-only. BM25, rank fusion, reranking, graph expansion, the evaluation harness, and CI are open. The reranker model is pinned and scored by doctor. It is not part of retrieval yet.
- Citation checks prove citations exist and resolve. They do not prove each claim is supported; that needs the milestone 4 fact checks.
- The stale-source answer is recorded, but the diagnosis write-up (lab part 8) is not done.
- No UI. Frontend work stays stopped until the screen list is specified.
- No rubric screenshots and no submission PDF.

## Next gate

Milestone 4: hand-written BM25 with an exact-identifier boost, reciprocal rank fusion with vector results, cross-encoder reranking, and at least eight fixed evaluation cases. It also adds the needle check per retrieval mode, a non-gating LLM-judge report, and the first live CI run.
