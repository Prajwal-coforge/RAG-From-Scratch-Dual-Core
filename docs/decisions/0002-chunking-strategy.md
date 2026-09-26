# 0002 — Chunking strategy

Status: implemented and used by ingestion since milestone 3, counting with the pinned Hugging Face EmbeddingGemma tokenizer.
Date: 2026-09-24

Parents are logical sections from Markdown headings or numbered headings such as `1. Purpose` and `2.1 Monthly minimum`. Children are passages inside one parent.

Defaults, counted by the caller-supplied tokenizer:

- target 300 tokens
- maximum 400 tokens
- overlap up to 50 tokens, and only whole trailing sentences
- a section that already fits under the maximum stays one child

A child never crosses a document version or a parent section. Overlap stays inside the same parent. Tables split into row groups that repeat the header. A condition and its exception stay in one child when they fit under the maximum; otherwise the condition chunk points at the exception chunk. A sentence over the maximum becomes labeled subspans with continuation links. Nothing is truncated to force a fit.

The previous character-window splitter in `src/policy_rag/chunking.py` is not this strategy.

Ingestion counts with `HFTokenizer` in `backend/app/embedder.py`, which wraps the tokenizer of the pinned sentence-transformers model, so chunk limits and the embedder's own length check use the same count. Chunk limits count the text tokens only; the pre-encode length check adds BOS and EOS. Unit tests pass word-counting tokenizers so they do not depend on the model files.

Before milestone 3 the chunker used `GemmaTokenizer` in `backend/app/chunking/gguf_tokenizer.py`, which reads the vocabulary inside the local Ollama `embeddinggemma` GGUF. On the generated corpus the two tokenizers agree on every line except 24 of 235, all headings ending in two spaces, where they differ by one token. The module stays for the milestone 1 record and its tests.
