from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICIES_DIR = Path(os.environ.get("POLICIES_DIR", ROOT / "policies"))
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", ROOT / ".chroma"))
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "policy_rag")

_OLLAMA_HOST: str | None = None


def ollama_host() -> str:
    """Prefer OLLAMA_HOST, else localhost, else Docker Desktop's Mac host."""
    global _OLLAMA_HOST
    if _OLLAMA_HOST:
        return _OLLAMA_HOST
    explicit = os.environ.get("OLLAMA_HOST")
    if explicit:
        _OLLAMA_HOST = explicit.rstrip("/")
        return _OLLAMA_HOST
    import urllib.error
    import urllib.request

    candidates = (
        "http://127.0.0.1:11434",
        "http://host.docker.internal:11434",
        "http://localhost:11434",
    )
    for host in candidates:
        try:
            with urllib.request.urlopen(f"{host}/api/tags", timeout=1.5) as resp:
                if resp.status == 200:
                    _OLLAMA_HOST = host
                    return host
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    _OLLAMA_HOST = candidates[0]
    return _OLLAMA_HOST


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "qwen3-embedding:0.6b")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen")

CHUNK_MAX_CHARS = int(os.environ.get("CHUNK_MAX_CHARS", "1500"))
CHUNK_OVERLAP_CHARS = int(os.environ.get("CHUNK_OVERLAP_CHARS", "180"))
VECTOR_K = int(os.environ.get("VECTOR_K", "8"))
KEYWORD_K = int(os.environ.get("KEYWORD_K", "8"))
RERANK_K = int(os.environ.get("RERANK_K", "4"))
RRF_K = int(os.environ.get("RRF_K", "60"))

CROSS_ENCODER_MODEL = os.environ.get(
    "CROSS_ENCODER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)
CHAT_TEMPERATURE = 0.0

QUERY_INSTRUCT = (
    "Given a company policy question, retrieve the relevant policy passage"
)


def format_query_for_embed(question: str) -> str:
    return f"Instruct: {QUERY_INSTRUCT}\nQuery: {question.strip()}"
