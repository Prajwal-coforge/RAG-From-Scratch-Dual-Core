# Implementation Tasks

Milestones 0, 1, and 2 are checked. Later milestones stay open. A checkbox requires its associated test or recorded evidence; creating code alone is insufficient. PROJECT_SPEC.md defines acceptance details.

## 0. Preflight and OpenSpec

- [x] 0.1 Read the full handoff and original assignment; record stack substitutions and corpus interpretation.
- [x] 0.2 Inspect existing workspace instructions and preserve unrelated files.
- [x] 0.3 Check OS, memory, accelerator, Python/Node, Docker, Ollama, and available CI options.
- [x] 0.4 Resolve and lock compatible dependencies, Memgraph image, models, and tokenizers.
- [x] 0.5 Initialize OpenSpec in the actual project and validate the proposed change without marking it implemented.
- [x] 0.6 Implement doctor checks for Memgraph, real embeddings, local chat, reranker, and tool calling.

## 1. Minimal proof before full ingestion

- [x] 1.1 Create two short known texts in an isolated smoke-test namespace.
- [x] 1.2 Embed the first text using Ollama and persist it in Memgraph.
- [x] 1.3 Add the second distinct text and create/inspect the actual Memgraph vector index.
- [x] 1.4 Query both texts and verify the expected nearest result using real services.
- [x] 1.5 Save timestamped terminal output, code commit, runtime versions, and index details before proceeding.

## 2. Sources, fixtures, and quality metadata

- [x] 2.1 Fetch only pinned allowlisted aviation sources; verify all three checksums and retain the upstream license.
- [x] 2.2 Generate four airport-policy documents through local Ollama and save prompts/raw outputs/model metadata.
- [x] 2.3 Validate each generated document's 500–800 prose-word count and explicit cross-policy links.
- [x] 2.4 Create current, duplicate, dirty-stale, and historical manifests with exact source hashes.
- [x] 2.5 Record the source corruption separately without altering original evidence.

## 3. Ingestion and basic RAG

- [x] 3.1 Implement numbered-text/Markdown parsers and reversible original-source offset mapping.
- [x] 3.2 Validate missing references, incompatible dates, metadata, and source duplicates.
- [x] 3.3 Implement section-aware parent–child chunking, bounded overlap, and table/exception handling.
- [x] 3.4 Implement formatted batched sentence-transformers EmbeddingGemma embeddings with a pre-encode token-limit refusal and configuration fingerprints; repeat the two-text proof with this embedder before full ingestion.
- [x] 3.5 Implement idempotent generation-based indexing, rollback, and source retirement.
- [x] 3.6 Implement vector retrieval over the Memgraph index with an exact-cosine check.
- [x] 3.7 Implement independent basic RAG CLI and local generation with resolvable citations.
- [x] 3.8 Add tests for source coverage, token overflow, model mismatch, and missing metadata.
- [x] 3.9 Capture full ingestion code and a real basic-RAG terminal demonstration.

## 4. Hybrid, reranking, and first evaluation

- [x] 4.1 Implement local BM25 keyword search with an exact-identifier boost, preserving identifiers, phrases, units, and negation.
- [x] 4.2 Implement documented rank fusion and stable chunk deduplication.
- [x] 4.3 Implement actual cross-encoder pair scoring and checked 512-token paired inputs.
- [x] 4.4 Implement parent/exception context packing and evidence-budget handling.
- [ ] 4.5 Draft and source-review 12 development and 12 held-out questions; include at least 8 generated-corpus cases in held-out.
- [x] 4.6 Freeze held-out labels and hashes before tuning; keep all evaluation artifacts out of ingestion.
- [x] 4.7 Implement pytest recall, deterministic answer facts, status, and citation metrics; report a non-gating LLM-judge support score and the needle retrieval ranks per mode.
- [x] 4.8 Run and capture a development query demonstrating hybrid improvement over vector-only.
- [x] 4.9 Run a real-service integration CI job; do not use skipped/mocked checks as submission evidence.

## 5. Graph, triage, and agents

- [x] 5.1 Build validated graph links with issuer/corpus scoping and source provenance. (Role, control, and department names in `data/graph/concepts.json` are agent-drafted and machine-checked; owner review pending.)
- [x] 5.2 Implement bounded graph expansion and explicit graph_rerank mode.
- [x] 5.3 Implement triage for corpus ambiguity, missing applicability facts, and cross-policy questions. (Deterministic; `data/graph/applicability.json` owner review pending. Known limitation found on held-out and left unfixed to avoid tuning on it: applicability is checked per section, so H-I02 (a rule for all pilots inside the rank-dependent Base Pay section) would get a false clarification.)
- [x] 5.4 Verify local Deep Agents/Ollama tool calling and inspect the full enabled tool inventory.
- [x] 5.5 Expose only allowlisted read tools; enforce request/step/time/delegation budgets and isolated state.
- [x] 5.6 Test prompt injection and absent-source behavior.
- [x] 5.7 Run a multi-policy scenario and preserve the graph paths and tool outcomes.

## 6. Frontend, experiments, diagnosis, and submission

- [ ] 6.1 Implement accessible JavaScript corpus selection, question/answer, citation drawer, and trace views.
- [ ] 6.2 Implement graph visualization and the evaluation screen.
- [ ] 6.3 Run frontend tests for unavailable services, conflicting sources, and citation display.
- [ ] 6.4 Compare chunking/overlap/model variants on development data and document decisions.
- [ ] 6.5 Run frozen held-out mode comparisons; retain actual metrics, per-case failures, latency, and configuration.
- [ ] 6.6 Run the dirty-stale source experiment; preserve the real flawed response and source-based diagnosis.
- [ ] 6.7 Re-run with the corrected source using the same question and pipeline; distinguish any remaining retrieval/generation failures.
- [ ] 6.8 Capture all eleven screenshot groups in assignment order and maintain the evidence manifest.
- [ ] 6.9 Run the full live submission CI lane with actual model access.
- [ ] 6.10 Generate and visually inspect the readable ordered submission PDF; append optional architecture/graph evidence afterward.
- [ ] 6.11 Verify every rubric row; never silently lower thresholds.
- [ ] 6.12 Update OpenSpec to verified behavior, archive only completed work, and write final reproduction instructions and limitations.
