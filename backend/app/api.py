"""HTTP API for the Ask screen. The CLI pipeline is unchanged.

Unknown JSON fields are rejected. Responses never include stored vectors.
A failure is a status and a short message, not a stack trace.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.ingest import connect
from app.retrieve import RetrievalRefused
from app.sources import SnapshotError
from app.triage import contexts

TRACES: dict[str, dict] = {}
TRACE_LIMIT = 100


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    corpus_id: str | None = None
    as_of: str | None = None
    mode: Literal["vector", "keyword", "hybrid", "hybrid_rerank", "graph_rerank"] | None = None
    include_history: bool = False


def list_corpora() -> list[dict]:
    """Contexts a person can select. The damaged dirty-stale snapshot is not one of them."""
    rows = []
    for ctx in contexts():
        rows.append(
            {
                "corpus_id": ctx["corpus_id"],
                "snapshot_id": ctx["snapshot_id"],
                "issuer": ctx["issuer"],
                "policies": [{"policy_id": pid, "title": title} for pid, title in sorted(ctx["policies"].items())],
            }
        )
    return rows


def _remember(report: dict) -> dict:
    trace_id = report["answer"]["trace_id"]
    body = {"trace_id": trace_id, "triage": report["triage"], "trace": _trace(report), "answer": _public_answer(report["answer"])}
    TRACES[trace_id] = body
    while len(TRACES) > TRACE_LIMIT:
        TRACES.pop(next(iter(TRACES)))
    return body


def _trace(report: dict) -> dict | None:
    retrieval = report.get("retrieval")
    if not retrieval:
        return None
    search = retrieval["search"]
    return {
        "mode": retrieval["mode"],
        "snapshot_id": retrieval["snapshot_id"],
        "corpus_id": retrieval["corpus_id"],
        "index_generation_id": retrieval["index_generation_id"],
        "as_of": retrieval["as_of"],
        "as_of_basis": retrieval.get("as_of_basis"),
        "include_history": retrieval["include_history"],
        "timing_ms": retrieval["timing_ms"],
        "stage_timing_ms": retrieval["stage_timing_ms"],
        "search": {
            "method": search["method"],
            "eligible": search["eligible"],
            "generation_chunks": search["generation_chunks"],
            "excluded": len(search["excluded"]),
            "stages": search["stages"],
        },
        "hits": [
            {
                "rank": hit["rank"],
                "chunk_id": hit["chunk_id"],
                "document_title": hit["document_title"],
                "heading_path": hit["heading_path"],
                "text": hit["text"],
                "signals": hit["signals"],
            }
            for hit in retrieval["hits"]
        ],
    }


def _public_answer(answer: dict) -> dict:
    kept = (
        "request_id", "trace_id", "status", "answer", "claims", "citations", "follow_up_questions",
        "mode_used", "corpus_id", "snapshot_id", "index_generation_id", "as_of", "timing_ms",
        "validation_problems", "evidence",
    )
    return {key: answer.get(key) for key in kept if key in answer}


def source_excerpt(chunk_id: str) -> dict:
    driver, _index = connect()
    try:
        with driver.session() as session:
            row = session.run(
                "MATCH (pub:Publication) "
                "MATCH (c:Chunk {chunk_id: $id, generation_id: pub.current}) "
                "RETURN c.chunk_id AS chunk_id, c.document_version_id AS document_version_id, "
                "c.document_title AS document_title, c.version AS version, c.heading_path AS heading_path, "
                "c.text AS text, c.source_spans AS source_spans, c.publication_status AS publication_status",
                id=chunk_id,
            ).single()
    finally:
        driver.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown source {chunk_id}")
    return dict(row)


def ready() -> dict:
    import httpx

    from app.doctor import load_lock

    lock = load_lock()
    try:
        driver, _index = connect()
        try:
            with driver.session() as session:
                session.run("RETURN 1 AS ok").single()
        finally:
            driver.close()
        httpx.get(f"{lock['ollama_url'].rstrip('/')}/api/version", timeout=3).raise_for_status()
    except Exception:
        raise HTTPException(status_code=503, detail="Memgraph or Ollama is not ready")
    return {"ready": True}


def ask(body: AskRequest) -> dict:
    from app.doctor import load_lock
    from app.embedder import embedder_from_lock
    from app.pipeline import ask_question
    from app.rerank import reranker_from_lock

    lock = load_lock()
    embedder = embedder_from_lock(lock)
    reranker = reranker_from_lock(lock)
    snapshot_id = None
    if body.corpus_id:
        match = next((row for row in list_corpora() if row["corpus_id"] == body.corpus_id), None)
        if match is None:
            raise HTTPException(status_code=422, detail=f"unknown corpus {body.corpus_id}")
        snapshot_id = match["snapshot_id"]
    driver, index = connect()
    try:
        with driver.session() as session:
            report = ask_question(
                session,
                index,
                embedder,
                body.question,
                reranker_for=lambda mode: reranker if mode in ("hybrid_rerank", "graph_rerank") else None,
                snapshot_id=snapshot_id,
                mode=body.mode,
                as_of=body.as_of,
                include_history=body.include_history,
            )
    finally:
        driver.close()
    return _remember(report)


def create_app(*, ask_fn=None, corpora_fn=None, source_fn=None, ready_fn=None) -> FastAPI:
    app = FastAPI(title="Airport Policy Assistant", docs_url=None, redoc_url=None)
    app.state.ask_fn = ask_fn or ask
    app.state.corpora_fn = corpora_fn or list_corpora
    app.state.source_fn = source_fn or source_excerpt
    app.state.ready_fn = ready_fn or ready

    @app.get("/api/health/live")
    def live():
        return {"live": True}

    @app.get("/api/health/ready")
    def ready_route():
        try:
            return app.state.ready_fn()
        except HTTPException:
            raise
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable", "detail": "The answer service is unavailable."})

    @app.get("/api/corpora")
    def corpora():
        return {"corpora": app.state.corpora_fn()}

    @app.post("/api/ask")
    def ask_route(body: AskRequest):
        try:
            return app.state.ask_fn(body)
        except HTTPException:
            raise
        except RetrievalRefused as exc:
            return JSONResponse(status_code=503, content={"status": "unavailable", "detail": str(exc)})
        except SnapshotError as exc:
            return JSONResponse(status_code=422, content={"status": "unavailable", "detail": str(exc)})
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable", "detail": "The answer service is unavailable."})

    @app.get("/api/traces/{trace_id}")
    def trace(trace_id: str):
        found = TRACES.get(trace_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"unknown trace {trace_id}")
        return found

    @app.get("/api/sources/{chunk_id}")
    def source(chunk_id: str):
        return app.state.source_fn(chunk_id)

    return app


app = create_app()
