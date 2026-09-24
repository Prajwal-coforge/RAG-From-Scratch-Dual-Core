# Preflight — 2026-09-24

Checked on this machine. The live doctor report is `docs/preflight/2026-09-24-doctor.json`. It is a runtime check, not a RAG evaluation.

| Check | Result |
| --- | --- |
| OS | darwin 25.6.0 |
| CPU | Apple M5, 10 cores |
| Memory | 24 GB (`hw.memsize` = 25769803776) |
| Accelerator | Metal, Apple M5. Ollama reports 17.8 GiB available |
| Python | Project runtime is CPython 3.12.14, installed with uv 0.12.18. `uv sync --group dev` creates `.venv`. The system `/usr/bin/python3` remains 3.9.6 and is not the backend runtime |
| Node | Cursor-bundled Node v26.8.1. `npm` is not on PATH. The React package lock waits until UI work starts |
| Docker | Client 29.8.0, server 29.7.2, daemon running |
| Ollama | Client and server 0.34.0, listening on `127.0.0.1:11434` |
| Chat model | `qwen3:8b`, blob `sha256:a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`. A temperature-0 chat returned a non-empty reply. The same model called the `add` tool |
| Embedding model | `embeddinggemma`, blob `sha256:0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515`. `/api/embed` with `truncate=false` returned one finite 768-dimensional vector. Tokenizer `embeddinggemma-gguf-spm-v1`. `nomic-embed-text` is installed and is not the selected embedder |
| Reranker | `cross-encoder/ms-marco-MiniLM-L6-v2` revision `233902d25c440f23af6f7d6e94d2946bac0bee0a` through sentence-transformers 6.1.0. One pair scored a finite value |
| Memgraph | Image `memgraph/memgraph-mage:3.13.0@sha256:cc33431b088c6b9580528d8d5aff92f3b958de1af5d40126f831ab8512eb855a`, container `airport-policy-memgraph`, Bolt `127.0.0.1:7687`. Index `chunk_embedding` is 768-d cosine, size 0. A probe node and the schema-preview policy were still present after `docker restart`. Lab image `memgraph/lab:3.7.1@sha256:4561711e0d7ef10825065c0823385e287f18b4f8abd5ad2d68fd0dabf5e12be8` |
| Dependencies | `uv.lock` resolves httpx 0.28.1, neo4j 6.3.1, sentence-transformers 6.1.0, torch 2.14.0, and pytest 9.1.1. Model and image pins are in `config/runtime.lock.json` |
| CI | No `.github/workflows` |
| OpenSpec | Change `build-airport-policy-rag` is in the repo for Cursor. It is not archived |

## Workspace inspection

The tree that was already here was the previous company-policy Chroma exercise: `src/policy_rag/`, its scripts, root tests, and presentation notes. That work belonged to this same lab, and it was removed so the handoff can start clean. Cursor OpenSpec commands under `.cursor/` stay. No separate unrelated project files were in the tree.

## Still outside this preflight

The two-text Memgraph retrieval proof is milestone 1. Generated policies, ingestion, access control, retrieval, evaluation, CI, and the UI are not started. `nomic-embed-text` must not replace `embeddinggemma`.
