# 0006 — Medallion zones without a data lake

Status: accepted for this project. Supersedes only the "medallion zones" phrase in `0001`.
Date: 2026-09-25

`0001` dropped a data lake and, with it, bronze/silver/gold zones. The project owner asked for the zone pattern anyway, on the condition that it not change ingestion, retrieval, citations, or index generations.

## What was added

`policy-rag etl --snapshot <id>` writes three JSON files under `.local/medallion/<snapshot>/`:

- **Bronze** records each landed file's path, size, and actual SHA-256. The bytes stay in `data/sources`.
- **Silver** runs `validate_snapshot` and `publication_decision`, the same gate ingest uses.
- **Gold** is written only when that gate allows publication. It is the chunk plan from `build_plan`, including the same generation id ingest would publish. Embeddings stay in the SQLite cache and in Memgraph.

Retrieval does not read these files. Re-running etl does not publish, roll back, or rewrite a source. `dirty-stale` still withholds gold unless `--profile evaluation --reason ...` is set.

## What stays out

No object store, lakehouse table format, warehouse, or Spark. The zones are local build artifacts, gitignored with the rest of `.local/`.
