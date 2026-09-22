# Policy RAG from scratch (dual-core)

Internal Q&A over Coforge policy PDFs. Retrieval is shared; generation is dual-core: **Qwen on Mac**, **extractive stub in CI**.

Architecture docs (same design, three views):

- [`docs/execution-graph.md`](docs/execution-graph.md) — pipelines and loops
- [`docs/rag-visual-board.md`](docs/rag-visual-board.md) — swimlane whiteboard
- [`docs/rag-presentation.md`](docs/rag-presentation.md) — slide deck (Markdown / Marp)

## End-to-end flow

```text
policies/*.pdf
    → extract + strip headers / TOC
    → section-aware recursive chunk (800–1500, overlap 150–200)
    → metadata: name, section, version
    → qwen3-embedding:0.6b → ChromaDB
                                    ┌→ vector top-k ─┐
question ──┬────────────────────────┤                ├→ RRF → CrossEncoder
           └→ keyword substring ────┘                      ↓
                                            prompt + top-k + metadata
                                                      ↓
                                         Ollama up? ──┬─ Mac: Qwen instruct (temp 0)
                                                      └─ CI: ExtractiveStub
                                                      ↓
                                            answer + document/section cites
```

## Corpus

PDFs live in `policies/`:

| Document | Notes |
| --- | --- |
| Whistleblower Policy | Numbered `1.0`–`14.0` (Context, Definitions, Reporting a Concern, …) |
| Related Party Transactions (RPT) | Numbered legal policy |
| Dividend Distribution Policy | Short `1.0` / `2.0` / `3.0` / `4.0` |
| Policy on Materiality of Events | Disclosure / materiality events |

Plant **one outdated duplicate** with conflicting details. That is the data-quality probe: if the right chunks come back, the bug is source data, not retrieval.

## Chunking

These files are numbered policies, so the chunk is a **section**, not a page and not a 400–500 character window.

1. Extract text; drop running headers, page numbers, and the table of contents.
2. Split on headings such as `1.0 Context` and `8.0 Reporting a Concern`.
3. If a section is still over ~1500 characters (Definitions, Investigation), recurse on `(a)` / `(b)`, then paragraphs, then sentences.
4. Target **800–1500 characters**, overlap **150–200**.
5. Attach `name`, `section`, `version` on every chunk.

`2.0 Objective` stays one chunk. `5.0 Definitions` becomes several chunks, all still labeled `5.0 Definitions`. Hybrid retrieval is meant to win on those section codes.

## Stack

| Role | Choice |
| --- | --- |
| Embeddings | Ollama `qwen3-embedding:0.6b` (query prefix only; chunks stored raw) |
| Vector store | ChromaDB |
| Hybrid | Vector top-k + keyword substring, merged with RRF |
| Rerank | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Generation · Mac | Local Qwen instruct, temperature 0 |
| Generation · CI | ExtractiveStub from top chunks + citations |

Do not embed with the Qwen chat model. Do not use Mistral. MiniLM is the reranker only.

Query prefix:

```text
Instruct: Given a company policy question, retrieve the relevant policy passage
Query: {question}
```

## Build order

Prove each layer before adding the next. If anything breaks, fall back to the two-text retrieve loop.

1. One text: embed + store in Chroma
2. Two texts: retrieve the relevant one
3. Section-chunk the full `policies/` corpus
4. Hybrid (vector + keyword → RRF)
5. CrossEncoder rerank
6. Eval harness (8+ gold questions) + CI

## Experiment knobs

Change one at a time: section max size (800 vs 1500), overlap (150 vs 200), top-k, hybrid vs vector, rerank on/off, Qwen vs extractive stub. Do not swap the embedder and the chat model in the same run.

## Lab mapping

This repo implements the from-scratch RAG lab against real Coforge policies instead of generated remote / expense / PTO text.

| Lab part | This project |
| --- | --- |
| 1 Source documents + planted issue | PDFs in `policies/` + one outdated duplicate |
| 2 Pipeline | Section chunk → Qwen embed → Chroma → Qwen / stub |
| 3 Hybrid retrieval | Substring + vector, RRF merge (wins on `8.0`, `5.0`) |
| 4 Rerank | CrossEncoder |
| 5 Eval harness | pytest: retrieval recall + key-fact accuracy, 8+ items |
| 6 Data-quality diagnosis | Two-question debug: retrieval vs source |
| 7 Source attribution | `name` + `section` on chunks and answers |
| 8 CI | ExtractiveStub so tests run without a chat model |
