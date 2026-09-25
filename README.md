# Airport Policy RAG

Local policy assistant for airport and airline staff. The build follows the handoff in [`airport-policy-rag-spec/START_HERE.md`](airport-policy-rag-spec/START_HERE.md). Status and open work are in [`docs/progress/2026-09-24-progress-report.md`](docs/progress/2026-09-24-progress-report.md).

The stack is local Ollama, Memgraph, a Python backend, and a React frontend. There is no data lake and no hosted model. The UI is not started.

## Corpus

Imported files are pinned from `DecisionsDev/policy-corpus` at commit `948dacad` and kept as separate issuers:

| Corpus | Issuer | File |
| --- | --- | --- |
| `skywings-baggage` | SkyWings Airlines | `data/sources/imported/luggage/luggage_policy.txt` |
| `aethersky-compensation` | AetherSky Airways | `data/sources/imported/human-resources/compensation/aethersky-airways-pilot-compensation-policy.txt` |
| `synthetic-emissions` | GAEA (fictional) | `data/sources/imported/air_transport/airplane_pollution_compliance.txt` |

The four generated AeroPolicy Airport documents are in `data/sources/generated/`: AP-BAG-001 v2 (current), AP-INC-002 v1, AP-SEC-003 v1, and the obsolete AP-BAG-001 v1. Their versions and dates are in `catalog.json`. The clean, duplicate, dirty-stale, and historical manifests are in `data/manifests/`.

```bash
uv run policy-rag corpus import      # fetch and verify the three pinned files
uv run policy-rag corpus generate    # refuses to overwrite without --force
uv run policy-rag corpus review      # apply recorded review edits
uv run policy-rag corpus manifests   # write-once manifests
```

The recorded generation runs are in [`docs/evidence/m2/`](docs/evidence/m2/README.md).

## Layout

| Path | Role |
| --- | --- |
| `airport-policy-rag-spec/` | Handoff specification |
| `openspec/changes/build-airport-policy-rag/` | Proposed change. Not implemented |
| `.cursor/commands/` | OpenSpec commands: `/opsx-explore`, `/opsx-propose`, `/opsx-apply`, `/opsx-update`, `/opsx-sync`, `/opsx-archive` |
| `backend/app/chunking/` | Section parent-child chunker |
| `backend/app/doctor.py` | Live runtime checks |
| `config/runtime.lock.json` | Pinned images, model digests, and reranker revision |
| `infra/compose.yaml` | Memgraph 3.13.0 and Lab 3.7.1 |
| `docs/decisions/` | Stack, chunking, and runtime-lock decisions |

## Run what exists

Install the locked backend and check the local runtime:

```bash
uv sync --group dev
uv run policy-rag doctor
```

`uv` provides CPython 3.12. Ollama must already be running, with `embeddinggemma` and `qwen3:8b` pulled. Memgraph must already be up.

Memgraph and Lab:

```bash
docker compose -f infra/compose.yaml up -d
```

Lab is at http://127.0.0.1:3000. The database Bolt port is `127.0.0.1:7687`. The graph currently loaded by `infra/schema-preview.cypher` is a schema preview, not ingested policy text.

Two-text retrieval proof (milestone 1). It embeds two known texts, stores them in Memgraph under their own `smoke_text_embedding` index, and checks that each question returns the right one:

```bash
uv run policy-rag smoke
uv run pytest -m live
```

The recorded run is in [`docs/evidence/m1/`](docs/evidence/m1/README.md).

Chunk the imported policies with the local EmbeddingGemma vocabulary:

```bash
PYTHONPATH=backend python scripts/chunk_imported_corpus.py
```

Chunk tests:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_chunking.py
```

Ollama must be running for embeddings. `embeddinggemma` is the embedding model. `qwen3:8b` is the planned local chat model.

## Still open

Milestones 0, 1, and 2 are recorded. Ingestion and basic RAG (milestone 3) are next. Retrieval, evaluation, CI, and the UI are still open.
