# Milestone 1 evidence — two-text retrieval proof

Rubric row "Minimal retrieval proof" (7 points), requirement EMB-02. Recorded 2026-09-24T21:25:10Z, before any policy text was ingested.

| File | Content |
| --- | --- |
| `2026-09-24T212509Z-terminal.txt` | Terminal output of `uv run policy-rag smoke` and `uv run pytest -m live` |
| `2026-09-24T212509Z-two-text-smoke.json` | Same run as JSON: commit, runtime versions, index details, stored texts, per-query scores |

## Run

| Item | Value |
| --- | --- |
| Code commit | `cbbbd9b9c0e77a86c206c9ec9a6e767060ebb1af`, clean tree |
| Ollama | 0.34.0, `embeddinggemma` blob `sha256:0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515`, 768 dimensions |
| Memgraph | 3.13.0 at `bolt://127.0.0.1:7687` |
| Smoke index | `smoke_text_embedding`, `label+property_vector` on `:SmokeText(embedding)`, 768 dimensions, cosine, f32, capacity 16 |
| Index size | 0 after creation, 1 after the first text, 2 after the second |
| Production index | `chunk_embedding` size 0 before and after |

Each stored vector was read back from Memgraph. All 768 values matched the Ollama embedding within 3.7e-09.

| Question | Rank 1 | Similarity | Rank 2 | Similarity |
| --- | --- | ---: | --- | ---: |
| How heavy can a checked suitcase be before it needs a special tag? | `m1-smoke:baggage` | 0.6242 | `m1-smoke:fuel-spill` | 0.1266 |
| Who should I tell about leaking jet fuel near a parked plane? | `m1-smoke:fuel-spill` | 0.5523 | `m1-smoke:baggage` | 0.2038 |

The questions share almost no words with the texts ("suitcase" against "bags", "leaking jet fuel near a parked plane" against "fuel spill on the apron"), so the ranking comes from the embeddings. Memgraph's `vector_search.search` similarity equals the exact cosine computed in Python over the stored vectors for every hit.

## Method

`backend/app/smoke.py`, entry point `policy-rag smoke`.

1. Refuse to run if the local `embeddinggemma` blob digest differs from `config/runtime.lock.json`.
2. Remove earlier `m1-smoke` nodes and the smoke index, then create the smoke vector index.
3. Embed the first text with `title: {title} | text: {text}` and `truncate=false`, store it, and read the vector back.
4. Do the same for the second text.
5. Embed each question with `task: search result | query: {question}` and call `vector_search.search`. A query passes when both the index and the exact cosine rank the expected text first with a positive margin.

Ollama's `embeddinggemma` template is `{{ .Prompt }}`, so it adds no prefix of its own. The prefixes are applied once, in `backend/app/embeddings.py`. Returned vectors are unit length.

## Finding for later ingestion

Memgraph 3.13.0 includes deleted nodes that are not yet garbage-collected in a vector index created right after the delete. On a rerun, the new smoke index reported size 2 before any insert, and `vector_search.search` then failed with "Trying to get a property from a deleted object." The reset now runs `FREE MEMORY` after the delete, and three consecutive reruns kept the sizes at 0, 1, 2. Reindexing and rollback in milestone 3 need the same handling.
