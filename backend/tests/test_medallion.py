import json

from pathlib import Path

from app.ingest import build_plan
from app.medallion import run_medallion
from app.sources import load_snapshot, sha256_bytes, validate_snapshot


def test_clean_zones_match_the_ingest_plan(make_embedder, tmp_path):
    embedder = make_embedder()
    report = run_medallion("clean", embedder, root=tmp_path)
    bronze = json.loads((tmp_path / "clean" / "bronze.json").read_text())
    silver = json.loads((tmp_path / "clean" / "silver.json").read_text())
    gold = json.loads((tmp_path / "clean" / "gold.json").read_text())
    snapshot = load_snapshot("clean")

    assert report["publishable"] and report["gold_chunks"] == len(gold["chunks"])
    for landed, doc in zip(bronze["documents"], snapshot.documents):
        assert landed["actual_sha256"] == sha256_bytes(Path(doc.path).read_bytes())
        assert landed["actual_sha256"] == doc.actual_sha256
    assert silver["findings"] == [finding.as_dict() for finding in validate_snapshot(snapshot)]
    plan = build_plan(snapshot, embedder)
    assert gold["generation_id"] == plan.generation_id
    assert [chunk["chunk_id"] for chunk in gold["chunks"]] == [chunk.chunk_id for chunk in plan.chunks]


def test_dirty_stale_stops_before_gold(make_embedder, tmp_path):
    source = Path(load_snapshot("dirty-stale").documents[0].path)
    before = sha256_bytes(source.read_bytes())
    report = run_medallion("dirty-stale", make_embedder(), root=tmp_path)
    gold = json.loads((tmp_path / "dirty-stale" / "gold.json").read_text())
    assert report["publishable"] is False and gold["chunks"] == [] and gold["generation_id"] is None
    assert sha256_bytes(source.read_bytes()) == before


def test_evaluation_profile_releases_gold_for_the_damaged_fixture(make_embedder, tmp_path):
    report = run_medallion(
        "dirty-stale", make_embedder(), profile="evaluation", reason="medallion gate check", root=tmp_path
    )
    assert report["publishable"] and report["gold_chunks"] > 0
