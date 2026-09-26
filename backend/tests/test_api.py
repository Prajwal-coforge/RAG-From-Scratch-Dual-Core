from fastapi.testclient import TestClient

from app.api import TRACES, AskRequest, create_app


def fake_ask(body: AskRequest) -> dict:
    TRACES.clear()
    from app.api import _remember

    return _remember(
        {
            "triage": {"status": "routed", "route": "direct_lookup", "corpus_id": body.corpus_id or "airport-generated", "mode": body.mode or "hybrid_rerank"},
            "retrieval": {
                "mode": "hybrid_rerank",
                "snapshot_id": "clean",
                "corpus_id": "airport-generated",
                "index_generation_id": "gen-test",
                "as_of": "2025-08-01",
                "include_history": False,
                "timing_ms": 12.0,
                "stage_timing_ms": {"rank_ms": 1.0},
                "search": {"method": "test", "eligible": 4, "generation_chunks": 4, "excluded": [], "stages": {}},
                "hits": [
                    {
                        "rank": 1,
                        "chunk_id": "chunk-1",
                        "document_title": "AP-BAG-001 v2 Staff Baggage",
                        "heading_path": "4 Escalation",
                        "text": "Escalate within 10 minutes.",
                        "signals": {"final_rank": 1},
                    }
                ],
            },
            "answer": {
                "request_id": "req-1",
                "trace_id": "trace-1",
                "status": "answered",
                "answer": "Escalate within 10 minutes [1].",
                "claims": [],
                "citations": [
                    {
                        "citation_id": 1,
                        "chunk_id": "chunk-1",
                        "document_title": "AP-BAG-001 v2 Staff Baggage",
                        "version": "2",
                        "section_path": "4 Escalation",
                        "excerpt": "Escalate within 10 minutes.",
                        "resolved": True,
                    }
                ],
                "follow_up_questions": [],
                "mode_used": "hybrid_rerank",
                "corpus_id": "airport-generated",
                "timing_ms": 3.0,
            },
        }
    )


def source_or_404(chunk_id: str) -> dict:
    from fastapi import HTTPException

    if chunk_id != "chunk-1":
        raise HTTPException(status_code=404, detail=f"unknown source {chunk_id}")
    return {"chunk_id": chunk_id, "text": "Escalate within 10 minutes."}


def client():
    corpora = [{"corpus_id": "airport-generated", "snapshot_id": "clean", "issuer": "AeroPolicy Airport", "policies": []}]
    return TestClient(create_app(ask_fn=fake_ask, corpora_fn=lambda: corpora, source_fn=source_or_404, ready_fn=lambda: {"ready": True}))


def test_corpora_and_ask_round_trip_keeps_the_trace():
    api = client()
    assert api.get("/api/corpora").json()["corpora"][0]["issuer"] == "AeroPolicy Airport"
    response = api.post("/api/ask", json={"question": "Who escalates a leaking bag?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["citations"][0]["excerpt"] == "Escalate within 10 minutes."
    assert "embedding" not in response.text
    assert api.get("/api/traces/trace-1").json()["trace"]["hits"][0]["chunk_id"] == "chunk-1"


def test_unknown_fields_and_long_questions_are_rejected():
    api = client()
    assert api.post("/api/ask", json={"question": "ok", "cypher": "MATCH (n) RETURN n"}).status_code == 422
    assert api.post("/api/ask", json={"question": "x" * 2001}).status_code == 422


def test_unknown_source_is_404_and_a_down_service_is_503_without_a_traceback():
    api = client()
    missing = api.get("/api/sources/missing")
    assert missing.status_code == 404 and "Traceback" not in missing.text

    down = TestClient(create_app(ready_fn=lambda: (_ for _ in ()).throw(RuntimeError("bolt down"))))
    response = down.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "The answer service is unavailable."
    assert "Traceback" not in response.text
