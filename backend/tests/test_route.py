from app.route import parse_route, route_corpora


def test_parse_route_keeps_catalog_ids_once():
    allowed = {"skywings-baggage", "airport-generated"}
    assert parse_route('{"corpus_ids": ["skywings-baggage", "nope", "skywings-baggage"]}', allowed) == ["skywings-baggage"]
    assert parse_route("not json", allowed) == []
    assert parse_route('{"corpus_ids": "skywings-baggage"}', allowed) == []


def test_a_failed_route_searches_every_published_context(monkeypatch):
    monkeypatch.setattr("app.route.contexts", lambda: (
        {"corpus_id": "a", "snapshot_id": "sa", "issuer": "Aero", "policies": {"P": "One"}},
        {"corpus_id": "b", "snapshot_id": "sb", "issuer": "Sky", "policies": {"Q": "Two"}},
    ))

    def down(_messages, **_kwargs):
        raise RuntimeError("ollama down")

    routed = route_corpora("what is the baggage limit?", chat_fn=down)
    assert routed["corpus_ids"] == ["a", "b"]
    assert routed["snapshot_ids"] == ["sa", "sb"]
    assert routed["status"] == "routed"
    assert "failed" in routed["basis"]
