"""Command line entry for the Airport Policy RAG lab."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.doctor import run_doctor, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="policy-rag")
    subcommands = parser.add_subparsers(dest="command", required=True)
    doctor = subcommands.add_parser("doctor", help="Check Memgraph, embeddings, chat, reranker, and tool calling")
    doctor.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    doctor.add_argument(
        "--restart-memgraph",
        action="store_true",
        help="Restart Memgraph and confirm the named volume kept a probe node",
    )
    smoke = subcommands.add_parser("smoke", help="Embed two known texts, store them in Memgraph, and retrieve")
    smoke.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    smoke.add_argument(
        "--embedder",
        choices=["sentence-transformers", "ollama"],
        default="sentence-transformers",
        help="ollama reproduces the milestone 1 run",
    )
    corpus = subcommands.add_parser("corpus", help="Import sources, generate policies, and build manifests")
    corpus_steps = corpus.add_subparsers(dest="step", required=True)
    corpus_steps.add_parser("import", help="Fetch and verify the three pinned aviation files")
    generate = corpus_steps.add_parser("generate", help="Generate the AeroPolicy documents with the local model")
    generate.add_argument("--only", nargs="+", help="Policy keys to generate, for example bag-v2")
    generate.add_argument("--force", action="store_true", help="Replace existing generated documents")
    corpus_steps.add_parser("review", help="Apply the recorded review edits to the accepted drafts")
    manifests = corpus_steps.add_parser("manifests", help="Build the four dataset manifests from the catalog")
    manifests.add_argument("--force", action="store_true", help="Replace manifests whose content changed")
    args = parser.parse_args(argv)
    if args.command == "corpus":
        return run_corpus(args)
    if args.command == "smoke":
        from app.smoke import run_smoke

        report = run_smoke(embedder_kind=args.embedder)
        if args.evidence:
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(report, indent=2) + "\n")
        return 0 if report["ok"] else 1
    if args.command == "doctor":
        checks, report = run_doctor(restart_memgraph=args.restart_memgraph)
        for check in checks:
            state = "ok" if check.ok else "failed"
            print(f"{state:6} {check.name}: {check.detail}")
        if args.evidence:
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(report, indent=2) + "\n")
        return summarize(checks)
    return 2


def run_corpus(args: argparse.Namespace) -> int:
    if args.step == "import":
        from app.corpus.imported import import_sources

        for row in import_sources():
            print(f"verified {row['corpus_id']}: {row['path']} {row['sha256'][:12]}")
        return 0
    if args.step == "generate":
        from app.corpus.generate import generate_all

        generate_all(keys=tuple(args.only) if args.only else None, force=args.force)
        return 0
    if args.step == "review":
        from app.corpus.review import apply_review

        for key, entry in apply_review()["documents"].items():
            print(f"{key}: {len(entry['review']['edits'])} edits  {entry['content_sha256'][:19]}")
        return 0
    from app.corpus.manifests import build_manifests, load_catalog, write_manifests

    sums = write_manifests(build_manifests(load_catalog()), force=args.force)
    for name, digest in sums.items():
        print(f"{name}: {digest[:19]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
