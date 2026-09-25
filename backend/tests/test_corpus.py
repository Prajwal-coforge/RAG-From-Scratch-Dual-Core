import hashlib
import json

import pytest

from app.corpus import imported
from app.corpus.generate import build_prompt, build_request, catalog_entry
from app.corpus.manifests import (
    MANIFESTS,
    ManifestError,
    build_manifests,
    load_catalog,
    validate_manifest,
    write_manifests,
)
from app.corpus.policies import BY_KEY, ESCALATION_CLAUSE, POLICIES
from app.corpus.validate import check_draft, count_prose_words

FILLER = "Staff follow this policy during every shift and record what they did in plain words. "


def draft(spec, sentences_per_section=12, body_extra=""):
    parts = [spec.heading, ""]
    for index, section in enumerate(spec.sections):
        parts.append(f"## {section}")
        text = FILLER * sentences_per_section
        if index == 0:
            text += " ".join(spec.references) + body_extra
        if section == spec.clause_section:
            text += " ".join(spec.verbatim)
        parts.extend([text, ""])
    return "\n".join(parts)


def test_a_complete_draft_passes():
    spec = BY_KEY["bag-v2"]
    report = check_draft(draft(spec, 7), spec)
    assert report.ok, report.problems
    assert 500 <= report.prose_words <= 800


def test_headings_do_not_count_as_prose():
    assert count_prose_words("# AP-BAG-001 Title\n## 1. Purpose\nOne two three.\n") == 3


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda t: t.replace("within 10 minutes", "within 12 minutes"), "missing required clause"),
        (lambda t: t.replace("AP-SEC-003", "the security policy"), "missing reference to AP-SEC-003"),
        (lambda t: t + "\nEscalate after 30 minutes if unsure.\n", "forbidden phrase"),
        (lambda t: t + "\n- a bullet\n", "list items"),
        (lambda t: t + "\nThis applies from 2025.\n", "date or version"),
        (lambda t: t + "\nSee AP-FUE-009 for fuel.\n", "do not exist"),
        (lambda t: t.replace("## 4. Baggage Incident Escalation", "## 4. Escalation"), "section headings"),
        (lambda t: "<think>plan</think>\n" + t, "first line"),
    ],
)
def test_draft_problems_are_reported(change, problem):
    spec = BY_KEY["bag-v2"]
    report = check_draft(change(draft(spec, 7)), spec)
    assert not report.ok
    assert any(problem in item for item in report.problems), report.problems


def test_the_deadline_must_sit_in_the_escalation_section():
    spec = BY_KEY["bag-v2"]
    text = draft(spec, 7)
    clause = spec.verbatim[0]
    moved = text.replace(clause, "").replace("## 3. Handling Standards\n", "## 3. Handling Standards\n" + clause + " ")
    assert any("not in section" in p for p in check_draft(moved, spec).problems)


def test_vague_timing_next_to_the_deadline_is_rejected():
    spec = BY_KEY["bag-v1"]
    text = draft(spec, 7).replace(spec.verbatim[0], "Report it immediately. " + spec.verbatim[0])
    assert any("'immediately'" in p for p in check_draft(text, spec).problems)
    assert check_draft(text.replace("Report it immediately. ", ""), spec).ok


def test_word_limits_are_enforced():
    spec = BY_KEY["inc-v1"]
    assert any("prose words" in p for p in check_draft(draft(spec, 2), spec).problems)
    assert any("prose words" in p for p in check_draft(draft(spec, 20), spec).problems)


def test_baggage_versions_differ_only_in_the_deadline():
    v1, v2 = BY_KEY["bag-v1"], BY_KEY["bag-v2"]
    assert v1.verbatim == (ESCALATION_CLAUSE.format(minutes=30),)
    assert v2.verbatim == (ESCALATION_CLAUSE.format(minutes=10),)
    assert v1.verbatim[0].replace("30 minutes", "10 minutes") == v2.verbatim[0]
    assert (v1.sections, v1.brief, v1.references) == (v2.sections, v2.brief, v2.references)


def test_current_baggage_policy_links_incident_and_restricted_items():
    assert set(BY_KEY["bag-v2"].references) == {"AP-INC-002", "AP-SEC-003"}


def test_prompt_and_request_carry_every_requirement():
    spec = BY_KEY["sec-v1"]
    request = build_request("qwen3:8b", spec, seed=3)
    assert request["think"] is False and request["stream"] is False
    assert request["options"]["seed"] == 3
    prompt = build_prompt(spec)
    assert request["messages"][1]["content"] == prompt
    assert spec.heading in prompt
    for item in (*spec.sections, *spec.verbatim, *spec.references):
        assert item in prompt


def test_a_rejected_draft_is_sent_back_with_its_problems():
    spec = BY_KEY["sec-v1"]
    request = build_request("qwen3:8b", spec, seed=2, previous=("short draft", ["485 prose words, outside 550-750"]))
    roles = [message["role"] for message in request["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert request["messages"][2]["content"] == "short draft"
    assert "485 prose words" in request["messages"][3]["content"]


def test_checksum_mismatch_is_refused_and_nothing_is_written(tmp_path, monkeypatch):
    target = tmp_path / "policy.txt"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"tampered"

    monkeypatch.setattr(imported.urllib.request, "urlopen", lambda url, timeout: Response())
    with pytest.raises(imported.ChecksumMismatch):
        imported.fetch_verified("https://example.invalid/p.txt", target, "0" * 64)
    assert not target.exists()
    good = hashlib.sha256(b"tampered").hexdigest()
    assert imported.fetch_verified("https://example.invalid/p.txt", target, good) == "tampered"
    assert target.read_bytes() == b"tampered"


def fake_catalog(tmp_path):
    documents = {}
    run = {"run_id": "test", "model": "qwen3:8b", "model_blob_digest": "sha256:x"}
    for spec in POLICIES:
        text = draft(spec, 7)
        (tmp_path / spec.filename).write_text(text)
        documents[spec.key] = catalog_entry(spec, text, text, run, {"seed": 1, "attempt_dir": "runs/test"})
    return {"corpus_id": "airport-generated", "documents": documents}


def test_manifests_have_the_required_contents(tmp_path):
    manifests = build_manifests(fake_catalog(tmp_path), tmp_path)
    ids = {name: [row["document_version_id"] for row in m["documents"]] for name, m in manifests.items()}
    bag1, bag2 = "airport-generated:AP-BAG-001:v1", "airport-generated:AP-BAG-001:v2"
    inc, sec = "airport-generated:AP-INC-002:v1", "airport-generated:AP-SEC-003:v1"
    assert sorted(ids["clean"]) == sorted([bag2, inc, sec])
    assert sorted(ids["duplicate"]) == sorted([bag1, bag2, inc, sec])
    assert sorted(ids["dirty-stale"]) == sorted([bag1, inc, sec])
    assert sorted(ids["historical"]) == sorted([bag1, bag2, inc, sec])
    assert all(m["as_of"] == "2025-08-01" for m in manifests.values())


def test_dirty_stale_records_the_corruption_and_keeps_the_original(tmp_path):
    catalog = fake_catalog(tmp_path)
    before = json.dumps(catalog, sort_keys=True)
    stale = build_manifests(catalog, tmp_path)["dirty-stale"]
    assert json.dumps(catalog, sort_keys=True) == before
    supplied = next(row for row in stale["documents"] if row["policy_id"] == "AP-BAG-001")
    assert supplied["publication_status"] == "active" and supplied["effective_to"] is None
    fixture = stale["fixture"]
    assert fixture["content_altered"] is False and fixture["evaluation_profile_only"] is True
    assert fixture["original_metadata"]["publication_status"] == "superseded"
    assert fixture["original_metadata"]["effective_to"] == "2025-06-30"
    assert fixture["missing_document_version_ids"] == ["airport-generated:AP-BAG-001:v2"]
    assert {c["field"] for c in fixture["corruptions"]} == {"publication_status", "effective_to"}
    assert supplied["content_sha256"] == catalog["documents"]["bag-v1"]["content_sha256"]


def test_duplicate_manifest_keeps_only_one_active_version(tmp_path):
    duplicate = build_manifests(fake_catalog(tmp_path), tmp_path)["duplicate"]
    statuses = {row["version"]: row["publication_status"] for row in duplicate["documents"] if row["policy_id"] == "AP-BAG-001"}
    assert statuses == {1: "superseded", 2: "active"}


def test_two_active_versions_are_rejected(tmp_path):
    manifest = build_manifests(fake_catalog(tmp_path), tmp_path)["duplicate"]
    for row in manifest["documents"]:
        row["publication_status"] = "active"
    with pytest.raises(ManifestError, match="more than one active"):
        validate_manifest(manifest, tmp_path)


def test_edited_source_is_rejected(tmp_path):
    catalog = fake_catalog(tmp_path)
    (tmp_path / "AP-BAG-001-v2.md").write_text("edited")
    with pytest.raises(ManifestError, match="does not match"):
        build_manifests(catalog, tmp_path)


def test_manifests_are_write_once(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    manifests = build_manifests(fake_catalog(sources), sources)
    out = tmp_path / "manifests"
    write_manifests(manifests, out)
    write_manifests(manifests, out)
    manifests["clean"]["purpose"] = "changed"
    with pytest.raises(ManifestError, match="write-once"):
        write_manifests(manifests, out)


@pytest.mark.skipif(not (MANIFESTS / "clean.json").exists(), reason="manifests not generated yet")
def test_committed_manifests_match_the_catalog_and_sources():
    rebuilt = build_manifests(load_catalog())
    sums = json.loads((MANIFESTS / "SHA256SUMS.json").read_text())
    for name, manifest in rebuilt.items():
        path = MANIFESTS / f"{name}.json"
        text = json.dumps(manifest, indent=2) + "\n"
        assert path.read_text() == text
        assert sums[path.name] == "sha256:" + hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.skipif(not (MANIFESTS / "clean.json").exists(), reason="documents not generated yet")
def test_committed_documents_pass_their_checks():
    catalog = load_catalog()
    from app.corpus.generate import GENERATED

    for key, entry in catalog["documents"].items():
        report = check_draft((GENERATED / entry["path"]).read_text(), BY_KEY[key])
        assert report.ok, (key, report.problems)
