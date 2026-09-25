from pathlib import Path

import pytest

from app.evaluation.cases import EVAL_ROOT, CaseError, check_freeze, document_texts, load_cases, load_clauses
from app.sources import ROOT, available_snapshots, load_snapshot


def test_every_clause_anchor_occurs_once_in_its_source():
    clauses = load_clauses()
    texts = document_texts()
    for clause in clauses.values():
        assert texts[clause.document_version_id][clause.start : clause.end] == clause.anchor


def test_suites_have_the_required_size_and_mix():
    dev, heldout = load_cases("dev"), load_cases("heldout")
    assert len(dev) >= 12 and len(heldout) >= 12
    assert sum(case.corpus_kind == "generated" for case in heldout) >= 8
    assert not {c.case_id for c in dev} & {c.case_id for c in heldout}
    assert not {c.question for c in dev} & {c.question for c in heldout}


def test_heldout_matches_its_freeze_record():
    frozen = check_freeze()
    assert frozen["case_count"] == len(load_cases("heldout"))


def test_evaluation_files_never_enter_a_snapshot():
    evaluation = EVAL_ROOT.resolve()
    questions = [case.question for split in ("dev", "heldout") for case in load_cases(split)]
    for snapshot_id in available_snapshots():
        for doc in load_snapshot(snapshot_id).documents:
            assert not Path(doc.path).resolve().is_relative_to(evaluation)
            assert not any(question in doc.text for question in questions)


def test_a_fact_missing_from_its_clauses_is_rejected(tmp_path, monkeypatch):
    import json

    import app.evaluation.cases as cases

    split = tmp_path / "dev"
    split.mkdir()
    raw = json.loads((EVAL_ROOT / "dev" / "cases.json").read_text())
    raw["cases"] = [raw["cases"][0]]
    raw["cases"][0]["required_answer_facts"] = [{"id": "wrong", "patterns": ["\\b45 minutes\\b"]}]
    (split / "cases.json").write_text(json.dumps(raw))
    monkeypatch.setattr(cases, "EVAL_ROOT", tmp_path)
    with pytest.raises(CaseError, match="not in the labelled clauses"):
        cases.load_cases("dev")
    assert ROOT.is_dir()
