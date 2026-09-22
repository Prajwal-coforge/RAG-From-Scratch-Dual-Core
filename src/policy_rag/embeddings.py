from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Sequence

from policy_rag.config import EMBED_MODEL, format_query_for_embed, ollama_host


class OllamaError(RuntimeError):
    pass


def ollama_available(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{ollama_host()}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _post(path: str, payload: dict, timeout: float = 120.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_host()}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(f"Ollama {path} failed ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise OllamaError(
            f"Ollama is not reachable at {ollama_host()}. "
            "On Mac it is already running if port 11434 is in use. "
            "From Docker/Cursor set OLLAMA_HOST=http://host.docker.internal:11434"
        ) from exc


def _embed_raw(texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        out = _post("/api/embed", {"model": EMBED_MODEL, "input": list(texts)})
        vectors = out.get("embeddings")
        if vectors:
            return vectors
    except OllamaError:
        if len(texts) != 1:
            raise
        out = _post("/api/embeddings", {"model": EMBED_MODEL, "prompt": texts[0]})
        if "embedding" in out:
            return [out["embedding"]]
        raise
    raise OllamaError(f"No embeddings returned for {EMBED_MODEL}")


def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    """Index path: raw chunk text, no query prefix."""
    return _embed_raw(texts)


def embed_query(question: str) -> list[float]:
    """Query path: instruct prefix required for qwen3-embedding."""
    return _embed_raw([format_query_for_embed(question)])[0]
