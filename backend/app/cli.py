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
    ingest = subcommands.add_parser("ingest", help="Validate a snapshot, build a new index generation, and publish it")
    ingest.add_argument("--snapshot", required=True, help="clean, duplicate, dirty-stale, historical, or imported:<corpus_id>")
    ingest.add_argument("--profile", choices=["ordinary", "evaluation"], default="ordinary")
    ingest.add_argument("--reason", help="Required with --profile evaluation; recorded on the generation")
    ingest.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    rollback = subcommands.add_parser("rollback", help="Republish the previous generation of a snapshot")
    rollback.add_argument("--snapshot", required=True)
    index = subcommands.add_parser("index", help="Show publication pointers and generations")
    index.add_argument("action", choices=["status", "reset"])
    index.add_argument("--yes", action="store_true", help="Confirm reset: delete every generation and pointer")
    ask = subcommands.add_parser("ask", help="Basic RAG: vector retrieval and a cited local answer")
    ask.add_argument("question")
    ask.add_argument("--snapshot", default="clean")
    ask.add_argument("--k", type=int, default=5)
    ask.add_argument("--as-of", help="ISO date; defaults to the snapshot's as_of")
    ask.add_argument(
        "--include-history",
        action="store_true",
        help="Use whichever version, including superseded ones, was in force on --as-of",
    )
    ask.add_argument("--json", action="store_true", help="Print the full JSON report")
    ask.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    args = parser.parse_args(argv)
    if args.command == "ask":
        return run_ask(args)
    if args.command == "corpus":
        return run_corpus(args)
    if args.command in ("ingest", "rollback", "index"):
        return run_index(args)
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


def run_ask(args: argparse.Namespace) -> int:
    from app.answer import answer_question
    from app.doctor import load_lock
    from app.embedder import embedder_from_lock
    from app.ingest import connect
    from app.retrieve import RetrievalRefused, retrieve

    embedder = embedder_from_lock(load_lock())
    driver, index = connect()
    try:
        with driver.session() as session:
            retrieval = retrieve(
                session,
                index,
                embedder,
                args.question,
                args.snapshot,
                k=args.k,
                as_of=args.as_of,
                include_history=args.include_history,
            )
    except RetrievalRefused as exc:
        print(f"refused: {exc}")
        return 4
    finally:
        driver.close()
    result = answer_question(retrieval, embedder.tokenizer)
    report = {"retrieval": retrieval, "answer": result}
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2) + "\n")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_ask(retrieval, result)
    return 0 if result["status"] in ("answered", "insufficient_evidence") else 1


def print_ask(retrieval: dict, result: dict) -> None:
    search = retrieval["search"]
    check = retrieval["exact_check"]
    print(f"question: {retrieval['question']}")
    print(
        f"snapshot {retrieval['snapshot_id']}  generation {retrieval['index_generation_id']}  as_of {retrieval['as_of']}  "
        f"mode {retrieval['mode']}  k {retrieval['k']}"
    )
    print(f"embedder {retrieval['embedder']['model']}@{retrieval['embedder']['revision'][:12]}  query input: {retrieval['query_input']}")
    print(f"search: {search['method']}; {search['eligible']} eligible of {search['generation_chunks']}, {len(search['excluded'])} excluded")
    grouped: dict[tuple[str, str], int] = {}
    for item in search["excluded"]:
        key = (item["document_version_id"], item["reason"])
        grouped[key] = grouped.get(key, 0) + 1
    for (version_id, reason), count in grouped.items():
        print(f"  excluded {count} chunk(s) of {version_id}: {reason}")
    print(f"exact cosine check: top-k agrees {check['top_k_agrees']}, max score gap {check['max_score_gap']:.2e}")
    print("retrieved:")
    for hit in retrieval["hits"]:
        print(
            f"  [{hit['rank']}] {hit['similarity']:.4f} (exact {hit['exact_cosine']:.4f})  "
            f"{hit['document_title']} / {hit['heading_path']}  chars {hit['source_spans'][0][0]}-{hit['source_spans'][-1][1]}"
        )
    generation = result.get("generation") or {}
    if generation:
        print(f"generation: {generation['model']} {generation['model_blob_digest'][:19]} options {generation['options']} think false")
    print(f"status: {result['status']}")
    for problem in result.get("validation_problems", []):
        print(f"  problem: {problem}")
    print("answer:")
    print(f"  {result['answer']}")
    print("citations:")
    for cite in result["citations"]:
        spans = ", ".join(f"{s}-{e}" for s, e in cite["source_spans"])
        print(
            f"  [{cite['citation_id']}] {cite['document_title']} / {cite['section_path']}  {cite['path']} chars {spans}  "
            f"resolved {cite['resolved']}"
        )
        excerpt = " ".join(cite["excerpt"].split())
        print(f"      \"{excerpt[:240]}{'…' if len(excerpt) > 240 else ''}\"")
    print(f"timing: retrieval {retrieval['timing_ms']} ms, answer {result['timing_ms']} ms")


def run_index(args: argparse.Namespace) -> int:
    from app.ingest import PublicationRefused, index_status, ingest, reset_index, rollback

    if args.command == "index":
        if args.action == "reset":
            if not args.yes:
                print("index reset deletes every generation and publication pointer; pass --yes to confirm")
                return 2
            reset_index()
            return 0
        print_status(index_status())
        return 0
    if args.command == "rollback":
        rollback(args.snapshot)
        return 0
    try:
        report = ingest(args.snapshot, profile=args.profile, reason=args.reason)
    except PublicationRefused:
        return 3
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2) + "\n")
    return 0


def print_status(status: dict) -> None:
    print(f"vector index {status['vector_index']} size {status['index_size']}")
    print("publications:")
    for row in status["publications"]:
        print(f"  {row['snapshot_id']:32} current {row['current']}  previous {row['previous']}")
    print("generations:")
    for row in status["generations"]:
        print(
            f"  {row['id']}  {row['snapshot_id']:32} {row['status']:9} profile {row['profile']:10} "
            f"chunks {row['stored_chunks']}/{row['chunk_count']}"
        )


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
