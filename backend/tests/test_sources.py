import dataclasses

import pytest

from app.sources import (
    SnapshotError,
    available_snapshots,
    load_snapshot,
    publication_decision,
    validate_snapshot,
)


def codes(findings, severity=None):
    return {f.code for f in findings if severity is None or f.severity == severity}


def replace_doc(snapshot, index, **changes):
    docs = list(snapshot.documents)
    docs[index] = dataclasses.replace(docs[index], **changes)
    snapshot.documents = docs
    return snapshot


def test_every_committed_snapshot_loads_with_matching_hashes():
    for snapshot_id in available_snapshots():
        snapshot = load_snapshot(snapshot_id)
        assert snapshot.documents
        for doc in snapshot.documents:
            assert doc.text
            assert doc.content_sha256 == doc.actual_sha256, doc.source_uri


def test_ordinary_snapshots_publish_and_the_damaged_fixture_does_not():
    for snapshot_id in ("clean", "duplicate", "historical"):
        allowed, _ = publication_decision(validate_snapshot(load_snapshot(snapshot_id)), profile="ordinary", reason=None)
        assert allowed, snapshot_id
    findings = validate_snapshot(load_snapshot("dirty-stale"))
    assert "evaluation_fixture" in codes(findings, "error")
    assert publication_decision(findings, profile="ordinary", reason=None)[0] is False
    assert publication_decision(findings, profile="evaluation", reason=None)[0] is False
    allowed, decision = publication_decision(findings, profile="evaluation", reason="stale-source diagnosis")
    assert allowed and "stale-source diagnosis" in decision


def test_the_stale_delivery_itself_passes_metadata_checks():
    findings = validate_snapshot(load_snapshot("dirty-stale"))
    assert codes(findings, "error") == {"evaluation_fixture"}


def test_missing_version_or_hash_refuses_ordinary_publication():
    for field in ("version", "content_sha256"):
        snapshot = replace_doc(load_snapshot("clean"), 0, **{field: None if field == "content_sha256" else ""})
        findings = validate_snapshot(snapshot)
        assert any(f.code == "missing_metadata" and field in f.message for f in findings), field
        allowed, decision = publication_decision(findings, profile="ordinary", reason=None)
        assert not allowed and "refused" in decision


def test_hash_mismatch_is_blocking():
    snapshot = replace_doc(load_snapshot("clean"), 1, content_sha256="sha256:" + "0" * 64)
    assert "hash_mismatch" in codes(validate_snapshot(snapshot), "error")


def test_two_active_versions_of_one_policy_conflict():
    snapshot = load_snapshot("duplicate")
    index = next(i for i, d in enumerate(snapshot.documents) if d.publication_status == "superseded")
    snapshot = replace_doc(snapshot, index, publication_status="active", effective_to=None)
    findings = validate_snapshot(snapshot)
    assert any(f.code == "conflicting_active_versions" and "AP-BAG-001" in f.message for f in findings)


def test_incompatible_dates_are_blocking():
    snapshot = replace_doc(load_snapshot("clean"), 0, effective_from="2025-07-01", effective_to="2025-01-01")
    assert "bad_dates" in codes(validate_snapshot(snapshot), "error")
    snapshot = replace_doc(load_snapshot("clean"), 0, effective_from="July 2025")
    assert "bad_dates" in codes(validate_snapshot(snapshot), "error")


def test_unresolved_references_are_warnings_not_invented_sections():
    findings = validate_snapshot(load_snapshot("imported:skywings-baggage"))
    refs = [f for f in findings if f.code == "unresolved_reference"]
    assert refs and all(f.severity == "warning" for f in refs)
    assert "Dangerous Goods Policy" in refs[0].message

    snapshot = load_snapshot("clean")
    snapshot.documents = [d for d in snapshot.documents if d.policy_id != "AP-SEC-003"]
    messages = [f.message for f in validate_snapshot(snapshot) if f.code == "unresolved_reference"]
    assert any("AP-SEC-003" in m for m in messages)


def test_reference_to_a_missing_section_is_flagged():
    snapshot = load_snapshot("clean")
    index = next(i for i, d in enumerate(snapshot.documents) if d.policy_id == "AP-INC-002")
    text = snapshot.documents[index].text.replace("AP-BAG-001 section 4", "AP-BAG-001 section 9")
    snapshot = replace_doc(snapshot, index, text=text)
    messages = [f.message for f in validate_snapshot(snapshot) if f.code == "unresolved_reference"]
    assert any("section 9" in m for m in messages)


def test_duplicate_content_keeps_both_identities():
    snapshot = load_snapshot("clean")
    copy = dataclasses.replace(snapshot.documents[0], document_version_id="airport-generated:COPY:v1", policy_id="COPY")
    snapshot.documents = [*snapshot.documents, copy]
    findings = [f for f in validate_snapshot(snapshot) if f.code == "duplicate_content"]
    assert findings and findings[0].severity == "warning"


def test_imported_corpora_are_separate_snapshots_with_unknown_dates_visible():
    snapshot = load_snapshot("imported:aethersky-compensation")
    assert snapshot.corpus_id == "aethersky-compensation"
    assert {d.corpus_id for d in snapshot.documents} == {"aethersky-compensation"}
    assert "unknown_effective_dates" in codes(validate_snapshot(snapshot), "warning")
    with pytest.raises(SnapshotError):
        load_snapshot("imported:not-a-corpus")
    with pytest.raises(SnapshotError):
        load_snapshot("not-a-snapshot")
