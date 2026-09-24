import json
from pathlib import Path

from app.doctor import Check, load_lock, summarize


def test_summarize_requires_every_check():
    assert summarize([Check("memgraph", True, "up"), Check("chat", True, "up")]) == 0
    assert summarize([Check("memgraph", True, "up"), Check("chat", False, "down")]) == 1
    assert summarize([]) == 1


def test_runtime_lock_pins_models_and_images():
    lock = load_lock()
    assert lock["embedding"]["dimensions"] == 768
    assert lock["embedding"]["blob_digest"].startswith("sha256:")
    assert lock["chat"]["model"] == "qwen3:8b"
    assert lock["reranker"]["revision"]
    assert lock["memgraph"]["digest"].startswith("sha256:")
    assert lock["memgraph"]["vector_index"] == "chunk_embedding"
    assert "/Users/" not in json.dumps(lock)
    assert ".ollama" not in json.dumps(lock)


def test_runtime_lock_file_is_in_the_repo():
    path = Path(__file__).resolve().parents[2] / "config" / "runtime.lock.json"
    assert path.is_file()
