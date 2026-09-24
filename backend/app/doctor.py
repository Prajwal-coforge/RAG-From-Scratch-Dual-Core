"""Live preflight checks for the local Airport Policy RAG runtime."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from neo4j import GraphDatabase

from app.chunking.gguf_tokenizer import MODEL_DIGEST, GemmaTokenizer, embeddinggemma_blob

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "config" / "runtime.lock.json"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def load_lock(path: Path = LOCK_PATH) -> dict:
    return json.loads(path.read_text())


def summarize(checks: list[Check]) -> int:
    return 0 if checks and all(check.ok for check in checks) else 1


def run_doctor(*, restart_memgraph: bool = False, lock_path: Path = LOCK_PATH) -> tuple[list[Check], dict]:
    lock = load_lock(lock_path)
    ollama = os.environ.get("OLLAMA_HOST", lock["ollama_url"]).rstrip("/")
    bolt = os.environ.get("MEMGRAPH_BOLT_URL", lock["memgraph"]["bolt_url"])
    checks = [
        check_memgraph(bolt, lock),
        check_embeddings(ollama, lock),
        check_tokenizer(lock),
        check_chat(ollama, lock),
        check_reranker(lock),
        check_tool_calling(ollama, lock),
    ]
    if restart_memgraph:
        checks.append(check_memgraph_persistence(bolt))
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": summarize(checks) == 0,
        "checks": [asdict(check) for check in checks],
    }
    return checks, report


def check_memgraph(bolt: str, lock: dict) -> Check:
    expected = lock["memgraph"]
    try:
        driver = GraphDatabase.driver(bolt, auth=None)
        with driver.session() as session:
            rows = session.run("CALL vector_search.show_index_info() YIELD * RETURN *").data()
        driver.close()
    except Exception as exc:
        return Check("memgraph", False, f"Bolt query failed: {exc.__class__.__name__}")
    match = next((row for row in rows if row.get("index_name") == expected["vector_index"]), None)
    if match is None:
        return Check("memgraph", False, f"vector index {expected['vector_index']} is missing")
    if int(match["dimension"]) != expected["vector_dimension"] or match["metric"] != expected["vector_metric"]:
        return Check("memgraph", False, "vector index dimension or metric does not match the lock")
    return Check(
        "memgraph",
        True,
        f"{expected['vector_index']} dimension {match['dimension']} metric {match['metric']} size {match['size']}",
    )


def check_memgraph_persistence(bolt: str, container: str = "airport-policy-memgraph") -> Check:
    probe_id = "m0-persistence-probe"
    driver = GraphDatabase.driver(bolt, auth=None)
    try:
        with driver.session() as session:
            session.run(
                "CREATE (:RuntimeProbe {id: $id, schema_sample: false})",
                id=probe_id,
            ).consume()
        subprocess.run(["docker", "restart", container], check=True, timeout=120)
        deadline = time.time() + 60
        found = False
        while time.time() < deadline:
            try:
                with driver.session() as session:
                    record = session.run(
                        "MATCH (n:RuntimeProbe {id: $id}) RETURN count(n) AS n",
                        id=probe_id,
                    ).single()
                found = record is not None and record["n"] == 1
                if found:
                    break
            except Exception:
                time.sleep(1)
                continue
            time.sleep(1)
        with driver.session() as session:
            session.run("MATCH (n:RuntimeProbe {id: $id}) DETACH DELETE n", id=probe_id).consume()
            sample = session.run(
                "MATCH (p:Policy {id: 'schema:policy:AP-BAG-001'}) RETURN count(p) AS n"
            ).single()
    except Exception as exc:
        return Check("memgraph_persistence", False, f"restart check failed: {exc.__class__.__name__}")
    finally:
        driver.close()
    if not found:
        return Check("memgraph_persistence", False, "probe node was missing after restart")
    if sample is None or sample["n"] != 1:
        return Check("memgraph_persistence", False, "schema preview policy was missing after restart")
    return Check("memgraph_persistence", True, "probe and schema preview survived a Memgraph restart")


def check_embeddings(ollama: str, lock: dict) -> Check:
    model = lock["embedding"]["model"]
    dimensions = lock["embedding"]["dimensions"]
    try:
        digest = _model_blob_digest(ollama, model)
        response = httpx.post(
            f"{ollama}/api/embed",
            json={"model": model, "input": "airport policy smoke", "truncate": False},
            timeout=120,
        )
        response.raise_for_status()
        vectors = response.json()["embeddings"]
    except Exception as exc:
        return Check("embeddings", False, f"embed request failed: {exc.__class__.__name__}")
    if digest != lock["embedding"]["blob_digest"]:
        return Check("embeddings", False, "embedding model blob does not match the lock")
    if len(vectors) != 1 or len(vectors[0]) != dimensions or not all(math.isfinite(value) for value in vectors[0]):
        return Check("embeddings", False, "embedding response was not one finite 768-dimensional vector")
    return Check("embeddings", True, f"{model} returned one finite {dimensions}-dimensional vector")


def check_tokenizer(lock: dict) -> Check:
    blob = embeddinggemma_blob()
    if not blob.is_file():
        return Check("tokenizer", False, "local embeddinggemma GGUF blob is not installed")
    if blob.name != MODEL_DIGEST.replace(":", "-"):
        return Check("tokenizer", False, "local embeddinggemma blob does not match the lock")
    if lock["embedding"]["tokenizer"] != GemmaTokenizer.name:
        return Check("tokenizer", False, "tokenizer name does not match the lock")
    tokenizer = GemmaTokenizer(blob)
    if tokenizer.count("the") != 1 or tokenizer.count("Hello world") != 2:
        return Check("tokenizer", False, "tokenizer counts did not match the EmbeddingGemma check")
    return Check("tokenizer", True, f"{tokenizer.name} counts 'the' as 1 and 'Hello world' as 2")


def check_chat(ollama: str, lock: dict) -> Check:
    model = lock["chat"]["model"]
    try:
        digest = _model_blob_digest(ollama, model)
        response = httpx.post(
            f"{ollama}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
                "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            },
            timeout=180,
        )
        response.raise_for_status()
        content = response.json()["message"].get("content") or ""
    except Exception as exc:
        return Check("chat", False, f"chat request failed: {exc.__class__.__name__}")
    if digest != lock["chat"]["blob_digest"]:
        return Check("chat", False, "chat model blob does not match the lock")
    if not content.strip():
        return Check("chat", False, "chat response was empty")
    return Check("chat", True, f"{model} returned a non-empty reply")


def check_reranker(lock: dict) -> Check:
    spec = lock["reranker"]
    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(spec["model"], revision=spec["revision"], max_length=spec["maximum_pair_tokens"])
        score = float(model.predict([("airport baggage allowance", "Bags must be tagged.")])[0])
    except Exception as exc:
        return Check("reranker", False, f"reranker failed: {exc.__class__.__name__}")
    if not math.isfinite(score):
        return Check("reranker", False, "reranker score was not finite")
    return Check("reranker", True, f"{spec['model']}@{spec['revision']} score {score:.4f}")


def check_tool_calling(ollama: str, lock: dict) -> Check:
    model = lock["chat"]["model"]
    try:
        response = httpx.post(
            f"{ollama}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
                "messages": [{"role": "user", "content": "Use the add tool with a=2 and b=2."}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "add",
                            "description": "Add two integers",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "a": {"type": "integer"},
                                    "b": {"type": "integer"},
                                },
                                "required": ["a", "b"],
                            },
                        },
                    }
                ],
            },
            timeout=180,
        )
        response.raise_for_status()
        message = response.json()["message"]
    except Exception as exc:
        return Check("tool_calling", False, f"tool-call request failed: {exc.__class__.__name__}")
    calls = message.get("tool_calls") or []
    names = [call.get("function", {}).get("name") for call in calls]
    if "add" not in names:
        return Check("tool_calling", False, "model did not call the add tool")
    return Check("tool_calling", True, f"{model} called add")


def _model_blob_digest(ollama: str, model: str) -> str:
    response = httpx.post(f"{ollama}/api/show", json={"model": model}, timeout=30)
    response.raise_for_status()
    modelfile = response.json().get("modelfile") or ""
    for line in modelfile.splitlines():
        if line.startswith("FROM "):
            token = line.split()[-1]
            if "sha256-" in token:
                return "sha256:" + token.rsplit("sha256-", 1)[-1]
    raise ValueError(f"{model} modelfile has no blob digest")
