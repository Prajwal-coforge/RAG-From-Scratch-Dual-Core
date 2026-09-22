# Policy RAG visual board

Whiteboard type: **vertical swimlane pipeline architecture** (stage-based RAG system map).

Open this file in Markdown preview to render the charts.

Corpus: Coforge PDFs in `policies/`. Chunking: **section-aware recursive split**. Dual-core generation: Ollama Qwen on Mac, extractive stub in CI. Do not embed with the chat model. Do not use Mistral. MiniLM is only the CrossEncoder.

---

## Locked model stack

| Role | Model | Runtime |
| --- | --- | --- |
| Embeddings | `qwen3-embedding:0.6b` | Ollama |
| Vector store | ChromaDB | local |
| Hybrid merge | Reciprocal Rank Fusion (RRF) | in-process |
| Rerank | `cross-encoder/ms-marco-MiniLM-L-6-v2` | sentence-transformers CrossEncoder |
| Generation · Mac | local Qwen instruct | Ollama, temperature 0 |
| Generation · CI | ExtractiveStub | no LLM; top chunks + citations |

Index chunks as raw text. Prefix **queries only**:

```text
Instruct: Given a company policy question, retrieve the relevant policy passage
Query: {question}
```

---

## 0. Data ingest and chunking flow

Numbered headings are the chunk boundaries. Recurse only when a section is still too long. Page-based and 400–500 character windows are out: pages already split sections, and 400 characters splits definitions.

```mermaid
flowchart TD
    pdfs[PDFs in policies/]
    extract[Extract text]
    clean[Strip headers footers TOC]
    version[Version to doc metadata]
    split[Split on numbered headings]
    long{Section over 1500 chars?}
    recurse[Recurse: clauses then paragraphs]
    chunk[Chunk 800-1500 overlap 150-200]
    meta[Attach name section version]
    embed[Embed raw text qwen3-embedding]
    store[ChromaDB]

    pdfs --> extract --> clean --> version --> split --> long
    long -->|no| chunk
    long -->|yes| recurse --> chunk
    chunk --> meta --> embed --> store
```

Example: Whistleblower `2.0 Objective` stays one chunk. `5.0 Definitions` splits on `(a)` / `(i)` but every piece still carries `section: 5.0 Definitions`.

---

## 1. Four-stage swimlane

```mermaid
flowchart LR
    subgraph dataCol ["1 · Data"]
        direction TB
        d1[Coforge policy PDFs]
        d2[Whistleblower / RPT / Dividend / Materiality]
        d3[Plant outdated duplicate]
        d4[Strip TOC headers footers]
        d5[Section-aware recursive chunk]
        d6[Meta: name, section, version]
        d1 --> d2 --> d3 --> d4 --> d5 --> d6
    end

    subgraph retrCol ["2 · Retrieval"]
        direction TB
        r1[Prove 2-text loop]
        r2[qwen3-embedding 0.6b]
        r3[ChromaDB store]
        r4[Vector top-k]
        r5[Keyword substring]
        r6[RRF merge]
        r7[CrossEncoder MiniLM]
        r1 --> r2 --> r3 --> r4 --> r5 --> r6 --> r7
    end

    subgraph genCol ["3 · Generation"]
        direction TB
        g1[Build prompt + metadata]
        g2{Ollama available?}
        g3[Qwen instruct · temp 0]
        g4[Extractive stub]
        g5[Answer + cite sources]
        g1 --> g2
        g2 -->|Mac| g3 --> g5
        g2 -->|CI| g4 --> g5
    end

    subgraph evalCol ["4 · Evals"]
        direction TB
        e1[8+ gold questions]
        e2[Retrieval recall]
        e3[Answer key facts]
        e4[Data-quality probe]
        e5[pytest + CI]
        e1 --> e2 --> e3 --> e4 --> e5
    end

    d6 --> r1
    r7 --> g1
    g5 --> e1
    e4 -.->|debug| d3
    e5 -.->|stuck| r1
```

---

## 2. Main runtime flow

This is the live query path. Vector and keyword run in parallel, merge with RRF, then rerank. Generation branches on whether Ollama is up.

```mermaid
flowchart TD
    q[UserQuestion]
    embed[EmbedQuery_QwenEmbed]
    chroma[ChromaVectorSearch]
    kw[KeywordSearch_substring]
    rrf[MergeCandidates_rrf]
    rerank[CrossEncoderRerank]
    prompt[BuildPrompt_topK_plus_metadata]
    ollama{OllamaAvailable}
    gen[Ollama_Qwen]
    stub[ExtractiveStub]
    out[AnswerPlusCitations]

    q --> embed --> chroma --> rrf
    q --> kw --> rrf
    rrf --> rerank --> prompt --> ollama
    ollama -->|yes_Mac| gen --> out
    ollama -->|no_CI| stub --> out
```

`EmbedQuery_QwenEmbed` is `qwen3-embedding:0.6b` with the query prefix. Hybrid wins on section codes such as `8.0` or `5.0 Definitions`.

```mermaid
sequenceDiagram
    actor User
    participant Embed as qwen3-embedding 0.6b
    participant Chroma as ChromaDB
    participant Keyword as Keyword match
    participant RRF as RRF merge
    participant Rerank as CrossEncoder
    participant LLM as Qwen or ExtractiveStub

    User->>Embed: natural-language question
    User->>Keyword: same question
    Note over Embed: query prefix only, not on chunks
    Embed->>Chroma: query embedding
    Chroma-->>RRF: vector top-k chunks
    Keyword-->>RRF: substring hits
    Note over RRF: hybrid wins on section codes
    RRF->>Rerank: fused candidates
    Rerank->>Rerank: rescore
    Rerank->>LLM: top-k chunks + metadata prompt
    alt Ollama available Mac
        Note over LLM: Qwen instruct temperature 0
    else CI no Ollama
        Note over LLM: ExtractiveStub from top chunks
    end
    LLM-->>User: answer + doc/section cites
```

---

## 3. Incremental build loop

```mermaid
flowchart TD
    A[1 text: embed + store] --> B[2 texts: retrieve]
    B -->|fail| A
    B -->|pass| C[Section-chunk full corpus]
    C --> D[Add hybrid RRF]
    D --> E[Add CrossEncoder]
    E --> F[Eval harness + CI]
    D -->|stuck| B
    E -->|stuck| B
    F -->|stuck| B
```

Prove A→B with Ollama `qwen3-embedding:0.6b` and Chroma before scaling.

---

## 4. Experiment loop

Change **one** knob only. Keep the Qwen embed and Qwen chat tags locked.

```mermaid
flowchart LR
    K[Change one knob] --> Q[Run known query]
    Q --> P{Pass?}
    P -->|yes| Keep[Keep]
    P -->|no| Revert[Revert]
    Keep --> K
    Revert --> K
```

| Knob | Compare |
| --- | --- |
| section max size | 800 vs 1500 chars |
| overlap | 150 vs 200 chars |
| top-k | default vs wider candidate set |
| retrieval | vector-only vs hybrid |
| rerank | CrossEncoder on vs off |
| generation | Qwen vs ExtractiveStub |

---

## 5. Two-question debug loop

Planted issue: **outdated duplicate** with conflicting details.

```mermaid
flowchart TD
    Q[Probe question] --> A[System answer]
    A --> R{Was it retrieval?}
    R -->|wrong chunks| Fix[Fix retrieve]
    R -->|right chunks| S{Was it source data?}
    S -->|conflict or gap| Planted[Planted duplicate]
    S -->|clean source| Gen[Check generation]
```

Diagnosis target: source data is wrong; retrieval and generation did their job.

---

## Stage stack

| Stage | Work | Stack |
| --- | --- | --- |
| Data | Coforge PDFs, plant outdated duplicate, section-aware recursive chunk, attach metadata | Whistleblower / RPT / Dividend / Materiality |
| Retrieval | 2-text loop, then scale; vector + keyword in parallel; RRF merge; CrossEncoder | Ollama `qwen3-embedding:0.6b`, ChromaDB, `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Generation | Prompt from top-k + metadata; Qwen on Mac, extractive stub in CI | Ollama Qwen instruct temp 0 · ExtractiveStub |
| Evals | 8+ gold items, recall + key facts, data-quality probe | pytest, CI |
