# Progress report — 2026-09-24

Airport Policy RAG overhaul. This report records what is in the working tree. It is not a claim that the lab is complete, and it is not instructor approval of the stack substitution.

OpenSpec change `build-airport-policy-rag` is proposed only. Milestone 0 tasks 0.1–0.6 and milestone 1 tasks 1.1–1.5 are checked. The other 42 tasks are open. Only the minimal retrieval proof (7 rubric points) has recorded evidence; its screenshot is not in a submission PDF yet. The UI has not been started. The change is not archived.

## Decisions

The assignment suggests sentence-transformers and Chroma. This project uses local Ollama and Memgraph instead. There is no data lake and no hosted model. Details are in `docs/decisions/0001-stack-substitution-and-corpus.md`.

On 2026-09-25 the data governance layer and local authentication were removed from the handoff and the OpenSpec change. The app serves one local user with no access control. Source lineage, versions, and the stale-source fixtures stay. Details are in `docs/decisions/0004-no-data-governance-layer.md`.

The imported corpus is three aviation files from `DecisionsDev/policy-corpus` at commit `948dacadbe03ca4d978ea3d6ccc19131e6a92efb`. Issuers stay separate. Four generated AeroPolicy documents are still required and do not exist yet. The old company-policy PDFs were removed from `policies/`.

## What is done

| Area | State |
| --- | --- |
| Handoff | `airport-policy-rag-spec/` is the specification. Stack and corpus choices are recorded. |
| Preflight | `docs/preflight/2026-09-24-environment.md`. Apple M5, 24 GB RAM, Metal available to Ollama. Doctor passed at 2026-09-24T20:32:08Z, including a Memgraph restart. |
| Ollama | 0.34.0 on `127.0.0.1:11434`. `embeddinggemma` returns 768-dimensional vectors. `qwen3:8b` is installed. |
| Memgraph | `memgraph/memgraph-mage:3.13.0` via `infra/compose.yaml`, bound to `127.0.0.1:7687`. Lab 3.7.1 is at `http://127.0.0.1:3000`. |
| Graph shape | Schema preview only, loaded by `infra/schema-preview.cypher`. Unique `id` constraints and an empty cosine index `chunk_embedding` (768 dimensions). Not ingested policy text. |
| OpenSpec | CLI 1.13.2 initialized for Cursor. Commands are `.cursor/commands/opsx-*.md`. `openspec validate` passed for `build-airport-policy-rag`. The change is not archived. |
| Chunking | `backend/app/chunking/`. Parent is one section. Child target is 300 EmbeddingGemma tokens, maximum 400, overlap at most 50 whole sentences. Version and section boundaries are not crossed. |
| Two-text proof | `policy-rag smoke` at commit `cbbbd9b`. Two texts embedded by `embeddinggemma`, stored in Memgraph under their own index `smoke_text_embedding`, and each question returned its expected text first (0.6242 vs 0.1266, 0.5523 vs 0.2038). Evidence in `docs/evidence/m1/`. `chunk_embedding` stayed at size 0. |
| Tests | 26 unit tests pass on Python 3.12.14. `pytest -m live` runs the real two-text test against Ollama and Memgraph and passed. |
| Imported sources | Three files fetched, SHA-256 checked, Apache-2.0 `LICENSE` kept under `data/sources/imported/`. |

Chunking run for the imported files, using the local EmbeddingGemma vocabulary. Every section was under 400 tokens, so each section is one child.

| Corpus | Sections | Children | Largest child |
| --- | ---: | ---: | ---: |
| `skywings-baggage` | 16 | 16 | 176 tokens |
| `aethersky-compensation` | 10 | 10 | 150 tokens |
| `synthetic-emissions` | 9 | 9 | 136 tokens |

SkyWings keeps headings such as `4 Checked Baggage Allowance`. AetherSky keeps `2.1 Base Pay`. GAEA keeps `Section 1 Emissions Monitoring` through `Section 8 Definitions`. Clause lines such as `1.1.` and quantities such as `2.5 kg` stay inside the parent. The chunk JSONL is a local build artifact at `.local/build/chunks/imported-chunks.jsonl` and is not committed.

## What is not done

- Host `npm` is not installed. OpenSpec commands were generated from package 1.13.2 and committed; a global `openspec` binary is not on `PATH`. The React package lock waits until UI work.
- The four generated AeroPolicy documents, including the obsolete duplicate, have not been created.
- No ingestion pipeline, retrieval, evaluation harness, or CI. The reranker model is pinned and scored by doctor. It is not part of retrieval yet.
- No UI. Frontend work stays stopped until the screen list is specified.
- No rubric screenshots and no submission PDF.

## Next gate

Milestone 2: generate the four airport policies through local Ollama with saved prompts and outputs, then chunk them with the same tokenizer. Memgraph keeps deleted nodes in a vector index created before garbage collection; ingestion and rollback must run `FREE MEMORY` after deletes, as `backend/app/smoke.py` does.
