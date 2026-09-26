import copy

from app.graph import load_concepts
from app.ingest import build_plan
from app.sources import load_snapshot


def graph_of(snapshot_id, make_embedder, concepts=None):
    plan = build_plan(load_snapshot(snapshot_id), make_embedder())
    if concepts is None:
        return plan.graph
    from app.graph import build_graph

    return build_graph(plan.documents, concepts)


def test_clean_snapshot_links_are_validated_with_source_spans(make_embedder):
    graph = graph_of("clean", make_embedder)
    assert graph.counts() == {"REFERENCES": 6, "APPLIES_TO_ROLE": 12, "MAPS_TO_CONTROL": 7, "OWNED_BY": 3, "unresolved": 0}
    snapshot = {d.document_version_id: d.text for d in load_snapshot("clean").documents}
    for link in graph.links:
        text = snapshot[link.document_version_id]
        assert link.evidence == text[link.start : link.end].strip()
        assert link.validation_status in ("validated", "exact-name-match", "reviewed-anchor")
        assert link.corpus_id == "airport-generated"
    refs = [l for l in graph.links if l.kind == "REFERENCES"]
    assert all(l.target in l.evidence for l in refs)
    assert all(l.target != l.document_version_id.split(":")[1] for l in refs)


def test_reference_outside_the_snapshot_is_unresolved_not_an_edge(make_embedder):
    graph = graph_of("imported:skywings-baggage", make_embedder)
    assert not [l for l in graph.links if l.kind == "REFERENCES"]
    [item] = graph.unresolved
    assert "Dangerous Goods Policy" in item["reference"] and "not in this snapshot" in item["reason"]


def test_concepts_are_scoped_by_corpus(make_embedder):
    graph = graph_of("imported:aethersky-compensation", make_embedder)
    assert graph.roles == [] and graph.controls == [] and graph.owned_by == []


def test_control_anchor_that_is_not_exact_is_unresolved(make_embedder):
    concepts = copy.deepcopy(load_concepts())
    control = concepts["corpora"]["airport-generated"]["controls"][0]
    for anchor in control["anchors"]:
        anchor["anchor"] = anchor["anchor"] + " (edited)"
    graph = graph_of("clean", make_embedder, concepts)
    assert not [l for l in graph.links if l.kind == "MAPS_TO_CONTROL" and l.target == control["id"]]
    assert any(u.get("control") == control["id"] for u in graph.unresolved)


def test_changing_the_concepts_changes_the_generation(make_embedder, tmp_path, monkeypatch):
    import app.graph as graph

    base = build_plan(load_snapshot("clean"), make_embedder()).generation_id
    edited = tmp_path / "concepts.json"
    edited.write_text(graph.CONCEPTS.read_text().replace("owner review pending", "owner reviewed"))
    monkeypatch.setattr(graph, "CONCEPTS", edited)
    assert build_plan(load_snapshot("clean"), make_embedder()).generation_id != base
