"""Two known texts embedded, stored in Memgraph, and retrieved.

Milestone 1 recorded this with the Ollama embedder. Milestone 3 repeats it
with the sentence-transformers embedder before full ingestion.

The smoke data uses its own label and vector index, so the production
chunk_embedding index stays empty until real ingestion.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from neo4j import GraphDatabase

from app.doctor import LOCK_PATH, _model_blob_digest, load_lock
from app.embedder import OllamaEmbedder, embedder_from_lock
from app.embeddings import cosine, format_document, format_query

ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = "m1-smoke"
LABEL = "SmokeText"
INDEX = "smoke_text_embedding"
INDEX_CAPACITY = 16
STORED_VECTOR_TOLERANCE = 1e-5


@dataclass(frozen=True)
class SmokeText:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class SmokeQuery:
    question: str
    expected_id: str


TEXTS = (
    SmokeText(
        id=f"{NAMESPACE}:baggage",
        title="Smoke test | Checked baggage",
        text="Checked bags heavier than 23 kg must carry a heavy-bag tag before they are loaded onto the aircraft.",
    ),
    SmokeText(
        id=f"{NAMESPACE}:fuel-spill",
        title="Smoke test | Apron safety",
        text="Report any fuel spill on the apron to the airside duty manager within 15 minutes and keep vehicles away.",
    ),
)

QUERIES = (
    SmokeQuery("How heavy can a checked suitcase be before it needs a special tag?", TEXTS[0].id),
    SmokeQuery("Who should I tell about leaking jet fuel near a parked plane?", TEXTS[1].id),
)


def make_embedder(kind: str, lock: dict, ollama: str):
    if kind == "ollama":
        spec = lock["ollama_embedding"]
        digest = _model_blob_digest(ollama, spec["model"])
        if digest != spec["blob_digest"]:
            raise RuntimeError(f"{spec['model']} blob {digest} does not match the lock; refusing to embed")
        return OllamaEmbedder(ollama, spec["model"], digest, spec["dimensions"])
    if kind == "sentence-transformers":
        return embedder_from_lock(lock)
    raise ValueError(f"unknown embedder {kind!r}")


def run_smoke(
    *,
    embedder_kind: str = "sentence-transformers",
    lock_path: Path = LOCK_PATH,
    ollama: str | None = None,
    bolt: str | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    lock = load_lock(lock_path)
    ollama = (ollama or lock["ollama_url"]).rstrip("/")
    bolt = bolt or lock["memgraph"]["bolt_url"]
    metric = lock["memgraph"]["vector_metric"]

    started = datetime.now(timezone.utc).isoformat()
    log(f"two-text smoke test  {started}")
    embedder = make_embedder(embedder_kind, lock, ollama)
    dimensions = embedder.dimensions
    digest = embedder.revision
    runtime = {
        "embedder": embedder.identity,
        "dimensions": dimensions,
        "document_format": format_document("{title}", "{text}"),
        "query_format": format_query("{question}"),
    }
    if embedder_kind == "ollama":
        runtime["ollama_version"] = httpx.get(f"{ollama}/api/version", timeout=10).json()["version"]
    else:
        import sentence_transformers

        runtime["sentence_transformers_version"] = sentence_transformers.__version__
    log(f"commit {git_commit()}  {embedder.runtime}  {embedder.model_id}@{digest[:19]}")

    driver = GraphDatabase.driver(bolt, auth=None)
    try:
        with driver.session() as session:
            runtime["memgraph_version"] = session.run("SHOW VERSION").single()["version"]
            log(f"memgraph {runtime['memgraph_version']} at {bolt}")

            production_before = production_size(session, lock)
            removed = reset_namespace(session)
            log(f"reset namespace {NAMESPACE}: removed {removed} old {LABEL} nodes, dropped old index if present")

            session.run(
                f"CREATE VECTOR INDEX {INDEX} ON :{LABEL}(embedding) "
                f'WITH CONFIG {{"dimension": {int(dimensions)}, "capacity": {INDEX_CAPACITY}, "metric": "{metric}"}}'
            ).consume()
            log(f"created vector index {INDEX} on :{LABEL}(embedding)")
            index_sizes = [index_info(session)["size"]]
            log(f"  index size {index_sizes[-1]}")

            stored = []
            for step, item in enumerate(TEXTS, start=1):
                formatted = format_document(item.title, item.text)
                vector = embedder.embed([formatted])[0]
                store_text(session, item, formatted, vector, digest)
                readback = read_vector(session, item.id)
                drift = max(abs(a - b) for a, b in zip(vector, readback))
                if len(readback) != dimensions or drift > STORED_VECTOR_TOLERANCE:
                    raise RuntimeError(f"stored vector for {item.id} does not match the embedding")
                index_sizes.append(index_info(session)["size"])
                stored.append(
                    {
                        "id": item.id,
                        "title": item.title,
                        "text": item.text,
                        "formatted_sha256": sha256(formatted),
                        "stored_dimensions": len(readback),
                        "max_readback_drift": drift,
                    }
                )
                log(f"step {step}: embedded and stored {item.id}")
                log(f"  text: {item.text}")
                log(f"  {len(readback)} values read back, max drift {drift:.2e}, index size {index_sizes[-1]}")

            info = index_info(session)
            log(
                f"index {info['index_name']}: {info['index_type']} {info['label']}({info['property']}) "
                f"dimension {info['dimension']} metric {info['metric']} {info['scalar_kind']} size {info['size']}"
            )

            vectors = {item.id: read_vector(session, item.id) for item in TEXTS}
            results = []
            for item in QUERIES:
                query_vector = embedder.embed([format_query(item.question)])[0]
                hits = search(session, query_vector, len(TEXTS))
                exact = {doc_id: cosine(query_vector, vec) for doc_id, vec in vectors.items()}
                exact_top = max(exact, key=exact.get)
                top = hits[0]["id"] if hits else None
                margin = hits[0]["similarity"] - hits[1]["similarity"] if len(hits) > 1 else None
                passed = top == item.expected_id and exact_top == item.expected_id and bool(margin and margin > 0)
                results.append(
                    {
                        "question": item.question,
                        "expected_id": item.expected_id,
                        "index_hits": hits,
                        "exact_cosine": exact,
                        "margin": margin,
                        "passed": passed,
                    }
                )
                log(f"query: {item.question}")
                for rank, hit in enumerate(hits, start=1):
                    log(
                        f"  [{rank}] {hit['id']}  index similarity {hit['similarity']:.4f}  "
                        f"exact cosine {exact[hit['id']]:.4f}"
                    )
                log(f"  expected {item.expected_id}: {'PASS' if passed else 'FAIL'}")

            production_after = production_size(session, lock)
            log(
                f"production index {lock['memgraph']['vector_index']} size {production_before} before, "
                f"{production_after} after"
            )
    finally:
        driver.close()

    untouched = production_before is not None and production_before == production_after
    ok = all(result["passed"] for result in results) and index_sizes == [0, 1, 2] and untouched
    log("PASS: both queries returned the expected text first" if ok else "FAIL: see results above")
    return {
        "checked_at": started,
        "ok": ok,
        "commit": git_commit(),
        "namespace": NAMESPACE,
        "runtime": runtime,
        "index": {**index_info_snapshot(info), "size_after_each_step": index_sizes},
        "production_index_size": {"before": production_before, "after": production_after},
        "stored": stored,
        "queries": results,
    }


def reset_namespace(session) -> int:
    if any(row["index_name"] == INDEX for row in all_index_info(session)):
        session.run(f"DROP VECTOR INDEX {INDEX}").consume()
    removed = session.run(f"MATCH (n:{LABEL}) RETURN count(n) AS n").single()["n"]
    session.run(f"MATCH (n:{LABEL}) DETACH DELETE n").consume()
    # A vector index created before garbage collection indexes the deleted nodes too.
    session.run("FREE MEMORY").consume()
    return int(removed)


def store_text(session, item: SmokeText, formatted: str, vector: list[float], digest: str) -> None:
    session.run(
        f"CREATE (:{LABEL} {{id: $id, namespace: $ns, title: $title, text: $text, "
        "formatted_sha256: $formatted_sha256, embedding_model_digest: $digest, embedding: $embedding})",
        id=item.id,
        ns=NAMESPACE,
        title=item.title,
        text=item.text,
        formatted_sha256=sha256(formatted),
        digest=digest,
        embedding=vector,
    ).consume()


def read_vector(session, doc_id: str) -> list[float]:
    record = session.run(
        f"MATCH (n:{LABEL} {{id: $id, namespace: $ns}}) RETURN n.embedding AS embedding",
        id=doc_id,
        ns=NAMESPACE,
    ).single()
    return list(record["embedding"]) if record else []


def search(session, query_vector: list[float], k: int) -> list[dict]:
    rows = session.run(
        "CALL vector_search.search($index, $k, $vector) YIELD node, similarity, distance "
        "WHERE node.namespace = $ns "
        "RETURN node.id AS id, similarity, distance ORDER BY similarity DESC",
        index=INDEX,
        k=k,
        vector=query_vector,
        ns=NAMESPACE,
    ).data()
    return [{"id": r["id"], "similarity": float(r["similarity"]), "distance": float(r["distance"])} for r in rows]


def production_size(session, lock: dict) -> int | None:
    name = lock["memgraph"]["vector_index"]
    row = next((row for row in all_index_info(session) if row["index_name"] == name), None)
    return row["size"] if row else None


def all_index_info(session) -> list[dict]:
    return session.run("CALL vector_search.show_index_info() YIELD * RETURN *").data()


def index_info(session) -> dict:
    match = next((row for row in all_index_info(session) if row["index_name"] == INDEX), None)
    if match is None:
        raise RuntimeError(f"vector index {INDEX} is missing")
    return match


def index_info_snapshot(info: dict) -> dict:
    keys = ("index_name", "index_type", "label", "property", "dimension", "metric", "scalar_kind", "capacity", "size")
    return {key: info[key] for key in keys}


def git_commit() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}-dirty" if dirty else sha


def sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
