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

Four generated AeroPolicy documents are still required and are not in the tree yet.

## Layout

| Path | Role |
| --- | --- |
| `airport-policy-rag-spec/` | Handoff specification |
| `openspec/changes/build-airport-policy-rag/` | Proposed change. Not implemented |
| `.cursor/commands/` | OpenSpec commands: `/opsx-explore`, `/opsx-propose`, `/opsx-apply`, `/opsx-update`, `/opsx-sync`, `/opsx-archive` |
| `backend/app/chunking/` | Section parent-child chunker |
| `infra/compose.yaml` | Memgraph 3.13.0 and Lab 3.7.1 |
| `docs/decisions/` | Stack and chunking decisions |

## Run what exists

Memgraph and Lab:

```bash
docker compose -f infra/compose.yaml up -d
```

Lab is at http://127.0.0.1:3000. The database Bolt port is `127.0.0.1:7687`. The graph currently loaded by `infra/schema-preview.cypher` is a schema preview, not ingested policy text.

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

The two-text Memgraph retrieval proof, generated policies, ingestion, access control, retrieval, evaluation, CI, and the UI. Python 3.11+ is the backend target. This machine was last checked at Python 3.9.6.
