# Preflight — 2026-09-24

Checked on this machine. Nothing here is a completed RAG run.

| Check | Result |
| --- | --- |
| OS | darwin 25.6.0 |
| CPU | Apple M5, 10 cores |
| Memory | 24 GB (`hw.memsize` = 25769803776) |
| Accelerator | Metal, Apple M5. Ollama reports 17.8 GiB available |
| Python | 3.9.6 at `/usr/bin/python3`. Project `.venv` is also 3.9.6. No Python 3.11+ on PATH |
| Node | Cursor-bundled Node v26.8.1. `npm`, `pnpm`, `yarn`, `bun`, and Homebrew are not installed |
| Docker | 29.8.0, daemon running. No Memgraph image pulled. `python:3.12-bookworm` and `node:latest` are already local |
| Ollama | Client and server 0.34.0, listening on `127.0.0.1:11434` |
| Chat model | `qwen3:8b` present (5.2 GB, Q4_K_M). Tool calling not exercised |
| Embedding model | `embeddinggemma` pulled during this preflight. Gemma3, 307.58M, BF16, embedding length 768, context 2048. Blob `sha256:0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515`. A live `/api/embed` call with `truncate=false` returned one finite 768-dimensional vector. `nomic-embed-text` is also installed and is not the selected embedder |
| Reranker | Not resolved. No pinned `sentence-transformers` revision yet |
| Memgraph | `memgraph/memgraph-mage:3.13.0` running as `airport-policy-memgraph` on `127.0.0.1:7687`. Image `sha256:cc33431b088c6b9580528d8d5aff92f3b958de1af5d40126f831ab8512eb855a`. `vector_search.search` is loaded. The database is empty |
| CI | No `.github/workflows` |
| OpenSpec CLI | Not installed, because no package manager is on PATH |

## Blockers before the two-text proof

1. Python 3.11 or newer on the host. The backend is specified to run on the host, not only in Docker.
2. The two-text vector index and retrieval proof. Memgraph is running, and no vector index has been created yet.
3. OpenSpec CLI initialization for Cursor. The proposed change files are in the repo. Slash-command generation still needs `openspec init --tools cursor`, and this machine has no npm.

`nomic-embed-text` must not be substituted for `embeddinggemma` in the baseline index.
