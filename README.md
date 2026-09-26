# Airport Policy RAG

Local policy assistant for airport and airline staff. The build follows the handoff in [`airport-policy-rag-spec/START_HERE.md`](airport-policy-rag-spec/START_HERE.md). Status and open work are in [`docs/progress/2026-09-24-progress-report.md`](docs/progress/2026-09-24-progress-report.md).

The stack is local: sentence-transformers EmbeddingGemma for embeddings, Memgraph for vectors and the policy graph, Ollama `qwen3:8b` for answers, a Python backend, and a React frontend. There is no data lake and no hosted model. The UI is not started.

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
| `openspec/changes/build-airport-policy-rag/` | Proposed change, not archived. Progress is in its `tasks.md` |
| `.cursor/commands/` | OpenSpec commands: `/opsx-explore`, `/opsx-propose`, `/opsx-apply`, `/opsx-update`, `/opsx-sync`, `/opsx-archive` |
| `backend/app/chunking/` | Section parent-child chunker |
| `backend/app/embedder.py` | Pinned sentence-transformers embedder with the over-limit refusal |
| `backend/app/sources.py` | Snapshot loading and pre-publication quality checks |
| `backend/app/ingest.py` | Generation-based Memgraph ingestion, publication, rollback, and retirement |
| `backend/app/retrieve.py` | Vector retrieval with eligibility filtering and the exact-cosine check |
| `backend/app/answer.py` | Local generation with validated, resolvable citations |
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

`uv` provides CPython 3.12. Ollama must already be running with `qwen3:8b` pulled. Memgraph must already be up.

The embedding model `google/embeddinggemma-300m` is gated on Hugging Face. Accept the Gemma license on the model page once, then run `uv run hf auth login` and paste your token at its prompt. The token stays in `~/.cache/huggingface/`; never put it in a command line or the repository. After the first download the model loads from the local cache.

Memgraph and Lab:

```bash
docker compose -f infra/compose.yaml up -d
```

Lab is at http://127.0.0.1:3000. The database Bolt port is `127.0.0.1:7687`. `infra/schema-preview.cypher` creates the constraints, the `chunk_embedding` index, and a few schema-preview nodes that the doctor's persistence check uses. Ingested policy text arrives through `policy-rag ingest`.

The Ask screen:

```bash
uv run uvicorn app.api:app --app-dir backend --host 127.0.0.1 --port 8000
cd frontend && npm install && npm run dev
```

Open http://127.0.0.1:5173. The page calls the local API. A question with no named issuer is routed by the local model across the published contexts. The damaged `dirty-stale` snapshot is not one of them. `--snapshot` on the CLI still forces one context for a lab run.

Two-text retrieval proof. It embeds two known texts, stores them in Memgraph under their own `smoke_text_embedding` index, and checks that each question returns the right one. `--embedder ollama` reproduces the milestone 1 run:

```bash
uv run policy-rag smoke
```

The recorded runs are in [`docs/evidence/m1/`](docs/evidence/m1/README.md) (Ollama) and [`docs/evidence/m3/`](docs/evidence/m3/README.md) (sentence-transformers).

## Ingest and ask

```bash
uv run policy-rag ingest --snapshot clean
uv run policy-rag ask "A baggage handler finds a leaking checked bag. Who must they escalate it to, and how quickly?"
uv run policy-rag index status
uv run policy-rag rollback --snapshot clean
```

Snapshots are `clean`, `duplicate`, `historical`, `dirty-stale`, and `imported:<corpus_id>`. `dirty-stale` is a damaged fixture and publishes only with `--profile evaluation --reason "..."`. `ask` uses the snapshot's `as_of` date by default. `--as-of` and `--include-history` answer from the version in force on another date. `--json` prints the full retrieval trace and answer report.

Each ingest builds a new index generation and moves the snapshot's publication pointer only after verification. Re-ingesting unchanged input does nothing. Runtime state (embedding cache and run records) is in `.local/state.sqlite`, which is not committed.

`policy-rag etl --snapshot clean` writes bronze, silver, and gold JSON for that snapshot under `.local/medallion/`. Bronze records landed file hashes, silver runs the same publication gate as ingest, and gold stores the chunk plan ingest would publish. These files are not a data lake and are not read by retrieval.

The recorded milestone 3 run is in [`docs/evidence/m3/`](docs/evidence/m3/README.md), produced by `scripts/record-m3-evidence.sh`.

## Tests

```bash
uv run pytest            # unit tests; no model or database needed
uv run pytest -m live    # real embedder, Memgraph, and Ollama
```

## Still open

Milestones 0 to 3 are recorded. Retrieval is vector-only. BM25 fusion, reranking, the evaluation harness, CI, graph relationships, agents, and the UI are open.
