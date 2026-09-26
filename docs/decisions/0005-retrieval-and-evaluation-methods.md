# 0005 — Embedding runtime, keyword method, answer grading, and needle check

Status: accepted for this project. Not instructor approval.
Date: 2026-09-25

## Embeddings through sentence-transformers

Part 2 of the assignment says to embed each chunk "with sentence-transformers". Embeddings move from Ollama `/api/embed` to sentence-transformers with the same model family, `google/embeddinggemma-300m`, at a pinned revision. Memgraph stays the vector store; that is the one remaining deviation from the assignment's suggested stack (Chroma), recorded in `0001`.

- The Hugging Face repository is gated (`gated: manual`, HTTP 401 without a token on 2026-09-25). Accept the Gemma license on the model page, then authenticate locally once. The token is never committed.
- Inputs are formatted once in code (`title: {title} | text: {text}`, `task: search result | query: {question}`) and encoded without the model's built-in `query`/`document` prompts, which would add a second prefix and force `title: none`.
- sentence-transformers truncates silently at `max_seq_length`, so every formatted input is counted with the model's tokenizer first and refused if it is over the limit.
- Ollama and sentence-transformers vectors for the "same" model are not interchangeable. The index fingerprint records the runtime, repository, and revision, and the two are never mixed in one index.
- The milestone 1 proof ran on Ollama and stays as recorded. The two-text proof is repeated with the sentence-transformers embedder before full ingestion (task 3.4).
- The chunk tokenizer counts with the same tokenizer the embedder uses: ingestion switched from `GemmaTokenizer` (GGUF vocabulary) to the Hugging Face tokenizer in milestone 3. See `0002`.
- The model loads from the local Hugging Face cache first and downloads only when the pinned revision is missing, so ordinary runs make no network request.

## Keyword retrieval: local BM25

Okapi BM25 written in the codebase, with no search library: k1 = 1.5 and b = 0.75, over child text plus title and heading. The tokenizer keeps policy identifiers (`AP-BAG-001`), section numbers (`4.2`), and number-unit pairs (`23 kg`) as single terms. A documented exact-match boost applies when a query identifier or quoted phrase appears verbatim. The BM25 score, the boost, and the rank are recorded per candidate. The keyword results are fused with the vector results by reciprocal rank fusion with constant 60.

The assignment accepts a substring match. BM25 is chosen because it weights rare terms over corpus-wide words such as "baggage" and is the standard lexical baseline.

## Answer grading: deterministic, with a reported judge

Required facts, prohibited facts, and expected status decide pass or fail, with exact numeric and unit matching. This matches the rubric's "answers contain expected key information", and it gives the same result on every CI run.

An LLM-judge support score is reported alongside. The local chat model rates each claim as supported or unsupported by the cited evidence, using a fixed rubric prompt at temperature 0. It never changes the outcome. It is the same model that wrote the answer, which is disclosed, and disagreements with the deterministic result are listed for manual review.

## Needle retrieval check

One unique synthetic sentence, such as a made-up form code, is added to an isolated evaluation index among the real chunks. It is requested by its code and by paraphrase, and the rank each mode (vector, keyword, hybrid, hybrid_rerank) gives it is recorded. The needle never enters a published index. This supplements the labeled source-clause recall; it does not replace it.
