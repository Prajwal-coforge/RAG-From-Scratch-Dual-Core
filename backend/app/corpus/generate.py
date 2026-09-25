"""Generate the four AeroPolicy documents with the locked local chat model.

Every attempt is saved with its exact request, the raw Ollama response, and
the check results. A document is accepted only when a draft passes every
check; failing drafts stay on disk as part of the record.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.corpus.policies import CORPUS_ID, ISSUER, OWNER, POLICIES, PolicySpec
from app.corpus.validate import check_draft
from app.doctor import LOCK_PATH, _model_blob_digest, load_lock
from app.smoke import git_commit

ROOT = Path(__file__).resolve().parents[3]
GENERATED = ROOT / "data" / "sources" / "generated"
CATALOG = GENERATED / "catalog.json"
MAX_ATTEMPTS = 6
OPTIONS = {"temperature": 0.4, "num_ctx": 8192, "num_predict": 2048}

SYSTEM_PROMPT = (
    "You write internal operating policies for AeroPolicy Airport, a fictional airport. "
    "Write in plain, formal English prose. Output only the policy document in Markdown, "
    "with no preamble and no closing remarks."
)


class GenerationFailed(RuntimeError):
    pass


def build_prompt(spec: PolicySpec) -> str:
    sections = "\n".join(f"## {name}" for name in spec.sections)
    clauses = "\n".join(f"- {clause}" for clause in spec.verbatim)
    others = ", ".join(spec.references)
    return (
        f"Write policy {spec.policy_id}, titled \"{spec.title}\", issued by {ISSUER}.\n\n"
        f"Content: {spec.brief}\n\n"
        f"Start with this exact first line:\n{spec.heading}\n\n"
        f"Then use exactly these section headings, in this order, and no other headings:\n{sections}\n\n"
        f"Include each of these sentences word for word in section \"{spec.clause_section}\":\n"
        f"{clauses}\n\n"
        f"Refer to the related policies by their IDs ({others}) where the text depends on them, "
        "and do not mention any other policy IDs.\n\n"
        "Rules:\n"
        "- Between 650 and 750 words of prose in total, not counting headings. "
        "Each section has two or three full paragraphs.\n"
        "- Paragraphs only. No bullet points, numbered lists, or tables.\n"
        "- Do not state any dates, years, or version numbers.\n"
        "- Do not state any time limit in minutes other than those in the required sentences.\n"
        + (
            f"- In section \"{spec.clause_section}\", do not use the words "
            + ", ".join(f'"{word}"' for word in spec.section_forbidden)
            + "; the required sentence is the only timing rule there.\n"
            if spec.section_forbidden
            else ""
        )
    )


def build_request(model: str, spec: PolicySpec, seed: int) -> dict:
    return {
        "model": model,
        "stream": False,
        "think": False,
        "options": {**OPTIONS, "seed": seed},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(spec)},
        ],
    }


def generate_all(
    *,
    keys: tuple[str, ...] | None = None,
    force: bool = False,
    lock_path: Path = LOCK_PATH,
    out_dir: Path = GENERATED,
    log: Callable[[str], None] = print,
) -> dict:
    lock = load_lock(lock_path)
    ollama = lock["ollama_url"].rstrip("/")
    model = lock["chat"]["model"]
    digest = _model_blob_digest(ollama, model)
    if digest != lock["chat"]["blob_digest"]:
        raise GenerationFailed(f"{model} blob {digest} does not match the lock; refusing to generate")
    specs = [spec for spec in POLICIES if keys is None or spec.key in keys]
    existing = [spec.filename for spec in specs if (out_dir / spec.filename).exists()]
    if existing and not force:
        raise GenerationFailed(f"{existing} already exist; generated sources are not overwritten without --force")

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = out_dir / "runs" / run_id
    run = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "commit": git_commit(),
        "ollama_version": httpx.get(f"{ollama}/api/version", timeout=10).json()["version"],
        "model": model,
        "model_blob_digest": digest,
        "system_prompt": SYSTEM_PROMPT,
        "options": OPTIONS,
        "documents": [],
    }
    log(f"generation run {run_id}  commit {run['commit']}  {model} {digest[:19]}")

    accepted: dict[str, tuple[PolicySpec, str, dict]] = {}
    for spec in specs:
        attempts = []
        for seed in range(1, MAX_ATTEMPTS + 1):
            request = build_request(model, spec, seed)
            response = httpx.post(f"{ollama}/api/chat", json=request, timeout=600)
            response.raise_for_status()
            body = response.json()
            raw = body["message"]["content"]
            report = check_draft(raw, spec)
            attempt_dir = run_dir / spec.key / f"attempt-{seed}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            (attempt_dir / "request.json").write_text(json.dumps(request, indent=2) + "\n")
            (attempt_dir / "response.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
            (attempt_dir / "raw.md").write_text(raw)
            checks = {"ok": report.ok, "prose_words": report.prose_words, "problems": report.problems}
            (attempt_dir / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
            attempts.append({"seed": seed, "raw_sha256": _sha(raw), **checks})
            state = "accepted" if report.ok else "rejected: " + "; ".join(report.problems)
            log(f"{spec.key} seed {seed}: {report.prose_words} words, {state}")
            if report.ok:
                accepted[spec.key] = (spec, raw, {"seed": seed, "attempt_dir": _rel(attempt_dir)})
                break
        run["documents"].append({"key": spec.key, "attempts": attempts})
        if spec.key not in accepted:
            _write_run(run_dir, run)
            raise GenerationFailed(f"{spec.key}: no draft passed the checks in {MAX_ATTEMPTS} attempts")

    run["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_run(run_dir, run)
    catalog = json.loads(CATALOG.read_text()) if CATALOG.exists() and out_dir == GENERATED else {"documents": {}}
    for key, (spec, raw, source) in accepted.items():
        final = raw.strip() + "\n"
        (out_dir / spec.filename).write_text(final)
        catalog["documents"][key] = catalog_entry(spec, final, raw, run, source)
        log(f"wrote {spec.filename}  {_sha(final)[:19]}")
    catalog["corpus_id"] = CORPUS_ID
    catalog["documents"] = dict(sorted(catalog["documents"].items()))
    (out_dir / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    return run


def catalog_entry(spec: PolicySpec, final: str, raw: str, run: dict, source: dict) -> dict:
    return {
        "document_version_id": spec.document_version_id,
        "corpus_id": CORPUS_ID,
        "policy_issuer": ISSUER,
        "policy_id": spec.policy_id,
        "version": spec.version,
        "title": spec.title,
        "source_type": "generated",
        "path": spec.filename,
        "content_sha256": _sha(final),
        "effective_from": spec.effective_from,
        "effective_to": spec.effective_to,
        "publication_status": spec.publication_status,
        "supersedes": spec.supersedes,
        "owner": OWNER,
        "license": "Generated for this lab; fictional content",
        "generation": {
            "run_id": run["run_id"],
            "model": run["model"],
            "model_blob_digest": run["model_blob_digest"],
            "seed": source["seed"],
            "attempt_dir": source["attempt_dir"],
            "raw_sha256": _sha(raw),
            "edits_after_generation": "surrounding whitespace stripped; no wording changed",
        },
    }


def _write_run(run_dir: Path, run: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
