# Policy RAG — data and retrieval

This pass covers **Data** and **Retrieval** only. Generation, evals, and CI are later.

Architecture docs (full system map, including later stages):

- [`docs/execution-graph.md`](docs/execution-graph.md)
- [`docs/rag-visual-board.md`](docs/rag-visual-board.md)
- [`docs/rag-presentation.md`](docs/rag-presentation.md)

## Retrieval flow

```text
policies/*.pdf
    → extract + strip headers / TOC
    → section-aware recursive chunk (800–1500, overlap 150–200)
    → metadata: name, section, version
    → qwen3-embedding:0.6b → ChromaDB
                                    ┌→ vector top-k ─┐
question ──┬────────────────────────┤                ├→ RRF → CrossEncoder
           └→ keyword substring ────┘                      ↓
                                            ranked chunks + citations metadata
```

## Corpus

PDFs live in `policies/`:

| Document | Notes |
| --- | --- |
| Whistleblower Policy | Numbered `1.0`–`14.0` |
| Related Party Transactions (RPT) | Numbered legal policy |
| Dividend Distribution Policy | Short `1.0` / `2.0` / `3.0` / `4.0` |
| Policy on Materiality of Events | Disclosure / materiality events |

## Chunking

1. Extract text; drop running headers, page numbers, and the table of contents.
2. Split on headings such as `1.0 Context` and `8.0 Reporting a Concern`.
3. If a section is still over ~1500 characters, recurse on `(a)` / `(b)`, then paragraphs, then sentences.
4. Target **800–1500 characters**, overlap **150–200**.
5. Attach `name`, `section`, `version` on every chunk.

## Stack

| Role | Choice |
| --- | --- |
| Embeddings | Ollama `qwen3-embedding:0.6b` (query prefix only; chunks stored raw) |
| Vector store | ChromaDB |
| Hybrid | Vector top-k + keyword substring, merged with RRF |
| Rerank | `cross-encoder/ms-marco-MiniLM-L-6-v2` |

Do not embed with a chat model. MiniLM is the reranker only.

Query prefix:

```text
Instruct: Given a company policy question, retrieve the relevant policy passage
Query: {question}
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 1–2. Prove embed → store → retrieve
python scripts/01_minimal_loop.py

# 3. Section-chunk policies/ into Chroma
python scripts/02_ingest.py

# 4. Print hybrid-retrieved chunks (no LLM answer)
python scripts/03_retrieve.py "What does section 8.0 say about reporting?"
```

From Docker/Cursor on a Mac, Ollama is auto-detected at `http://host.docker.internal:11434`. Override with `OLLAMA_HOST` if needed.

Install CrossEncoder only when you want rerank:

```bash
pip install -e ".[dev,rerank]"
```

```bash
pytest -q
```

## Experiment knobs

Change one at a time: section max size (800 vs 1500), overlap (150 vs 200), top-k, hybrid vs vector, rerank on/off.
