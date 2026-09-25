# 0002 — Chunking strategy

Status: implemented for unit tests. The EmbeddingGemma tokenizer is not wired in yet.
Date: 2026-09-24

Parents are logical sections from Markdown headings or numbered headings such as `1. Purpose` and `2.1 Monthly minimum`. Children are passages inside one parent.

Defaults, counted by the caller-supplied tokenizer:

- target 300 tokens
- maximum 400 tokens
- overlap up to 50 tokens, and only whole trailing sentences
- a section that already fits under the maximum stays one child

A child never crosses a document version or a parent section. Overlap stays inside the same parent. Tables split into row groups that repeat the header. A condition and its exception stay in one child when they fit under the maximum; otherwise the condition chunk points at the exception chunk. A sentence over the maximum becomes labeled subspans with continuation links. Nothing is truncated to force a fit.

The previous character-window splitter in `src/policy_rag/chunking.py` is not this strategy.

Corpus runs use `GemmaTokenizer` in `backend/app/chunking/gguf_tokenizer.py`. It reads the sentencepiece vocabulary inside the local Ollama `embeddinggemma` GGUF and merges pieces the same way that model does. Checked against Ollama `/api/embed` `prompt_eval_count`: the embed request is the text tokens plus BOS and EOS. Chunk limits count the text tokens only. Unit tests still pass `WordTokenizer` so they do not depend on the model file.
