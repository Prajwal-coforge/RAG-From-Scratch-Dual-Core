# 0003 — Runtime lock

Status: accepted for this project. Not instructor approval.
Date: 2026-09-24

Milestone 0 resolves the runtime on the host instead of leaving versions unnamed.

- Python dependencies are locked by `uv.lock` after `uv lock` against PyPI. The project environment is CPython 3.12.14 from uv 0.12.18. The system Python 3.9.6 is not used.
- Memgraph and Lab image digests are pinned in `infra/compose.yaml` and `config/runtime.lock.json`.
- `embeddinggemma` and `qwen3:8b` are pinned by the Ollama blob digests recorded from the local manifests.
- The reranker revision is the Hugging Face commit `233902d25c440f23af6f7d6e94d2946bac0bee0a` for `cross-encoder/ms-marco-MiniLM-L6-v2`. Doctor loads that revision and scores one pair.
- The React package lock is deferred. UI work has not started, so no frontend dependencies were installed or invented.

`policy-rag doctor` checks Memgraph, a real embedding, the tokenizer, local chat, the reranker, and one tool call. `--restart-memgraph` checks that the named volume survives a container restart. The 2026-09-24 run passed and is stored in `docs/preflight/2026-09-24-doctor.json`.
