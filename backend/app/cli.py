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
    etl = subcommands.add_parser("etl", help="Write bronze, silver, and gold zone files for a snapshot")
    etl.add_argument("--snapshot", required=True, help="clean, duplicate, dirty-stale, historical, or imported:<corpus_id>")
    etl.add_argument("--profile", choices=["ordinary", "evaluation"], default="ordinary")
    etl.add_argument("--reason", help="Required with --profile evaluation when the snapshot has blocking findings")
    etl.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    rollback = subcommands.add_parser("rollback", help="Republish the previous generation of a snapshot")
    rollback.add_argument("--snapshot", required=True)
    index = subcommands.add_parser("index", help="Show publication pointers and generations")
    index.add_argument("action", choices=["status", "reset"])
    index.add_argument("--yes", action="store_true", help="Confirm reset: delete every generation and pointer")
    ask = subcommands.add_parser("ask", help="Retrieve evidence and answer with validated citations")
    ask.add_argument("question")
    ask.add_argument("--snapshot", help="Force one snapshot. When omitted, a named issuer is used, otherwise the local model chooses")
    ask.add_argument("--corpus", help="Select the context by corpus id instead, for example airport-generated")
    ask.add_argument(
        "--mode",
        choices=["vector", "keyword", "hybrid", "hybrid_rerank", "graph_rerank"],
        help="Default: chosen by triage (hybrid_rerank, or graph_rerank for cross-policy questions)",
    )
    ask.add_argument("--k", type=int, default=5)
    ask.add_argument("--as-of", help="ISO date; defaults to the snapshot's as_of")
    ask.add_argument(
        "--include-history",
        action="store_true",
        help="Use whichever version, including superseded ones, was in force on --as-of",
    )
    ask.add_argument("--json", action="store_true", help="Print the full JSON report")
    ask.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    agent = subcommands.add_parser("agent", help="Answer with the bounded local Deep Agents mode")
    agent.add_argument("question")
    agent.add_argument("--snapshot", help="Force one snapshot. When omitted, routing chooses the context")
    agent.add_argument("--as-of", help="ISO date; defaults to the snapshot's as_of")
    agent.add_argument("--include-history", action="store_true")
    agent.add_argument("--json", action="store_true", help="Print the full JSON report")
    agent.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    evaluate = subcommands.add_parser("evaluate", help="Run an evaluation suite across retrieval modes")
    evaluate.add_argument("--suite", choices=["dev", "heldout"], required=True)
    evaluate.add_argument("--modes", default="vector,keyword,hybrid,hybrid_rerank,graph_rerank", help="Comma-separated retrieval modes")
    evaluate.add_argument("--cases", help="Comma-separated case ids; default all")
    evaluate.add_argument("--retrieval-only", action="store_true", help="Skip generation, fact checks, and the judge")
    evaluate.add_argument("--no-judge", action="store_true", help="Skip the non-gating LLM judge")
    evaluate.add_argument("--no-needle", action="store_true", help="Skip the isolated needle check")
    evaluate.add_argument("--evidence", type=Path, help="Write the JSON report to this path")
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        return run_evaluate(args)
    if args.command == "ask":
        return run_ask(args)
    if args.command == "agent":
        return run_agent_command(args)
    if args.command == "corpus":
        return run_corpus(args)
    if args.command == "etl":
        return run_etl(args)
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


def run_evaluate(args: argparse.Namespace) -> int:
    from app.evaluation.run import evaluate, print_summary, timestamp
    from app.sources import ROOT

    report = evaluate(
        args.suite,
        [m.strip() for m in args.modes.split(",") if m.strip()],
        answers=not args.retrieval_only,
        judge=not (args.retrieval_only or args.no_judge),
        needle=not args.no_needle,
        case_ids=[c.strip() for c in args.cases.split(",")] if args.cases else None,
    )
    path = args.evidence or ROOT / ".local" / "evaluations" / f"{timestamp()}-{args.suite}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print_summary(report)
    print(f"report: {path}")
    return 0


def run_ask(args: argparse.Namespace) -> int:
    from app.doctor import load_lock
    from app.embedder import embedder_from_lock
    from app.ingest import connect
    from app.pipeline import ask_question
    from app.rerank import reranker_from_lock
    from app.retrieve import RERANKED, RetrievalRefused
    from app.sources import load_snapshot

    from app.triage import contexts

    snapshot_id = args.snapshot
    if args.corpus:
        serving = {c["corpus_id"]: c["snapshot_id"] for c in contexts()}
        if args.corpus not in serving:
            print(f"unknown corpus {args.corpus!r}; choose from {', '.join(serving)}")
            return 2
        if snapshot_id and load_snapshot(snapshot_id).corpus_id != args.corpus:
            print(f"snapshot {snapshot_id} is not in corpus {args.corpus}")
            return 2
        snapshot_id = snapshot_id or serving[args.corpus]
    lock = load_lock()
    embedder = embedder_from_lock(lock)
    driver, index = connect()
    try:
        with driver.session() as session:
            report = ask_question(
                session,
                index,
                embedder,
                args.question,
                reranker_for=lambda mode: reranker_from_lock(lock) if mode in RERANKED else None,
                snapshot_id=snapshot_id,
                mode=args.mode,
                k=args.k,
                as_of=args.as_of,
                include_history=args.include_history,
            )
    except RetrievalRefused as exc:
        print(f"refused: {exc}")
        return 4
    finally:
        driver.close()
    result = report["answer"]
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2) + "\n")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_triage(report["triage"])
        if report["retrieval"]:
            print_ask(report["retrieval"], result)
        else:
            print(f"status: {result['status']}\nanswer:\n  {result['answer']}")
            for follow_up in result["follow_up_questions"]:
                print(f"  follow-up: {follow_up}")
    return 0 if result["status"] in ("answered", "insufficient_evidence", "needs_clarification") else 1


def run_agent_command(args: argparse.Namespace) -> int:
    from app.agent.run import run_agent
    from app.doctor import load_lock
    from app.embedder import embedder_from_lock
    from app.ingest import connect
    from app.rerank import reranker_from_lock
    from app.retrieve import RetrievalRefused

    lock = load_lock()
    embedder = embedder_from_lock(lock)
    driver, index = connect()
    try:
        with driver.session() as session:
            report = run_agent(session, index, embedder, reranker_from_lock(lock), args.question, snapshot_id=args.snapshot,
                               as_of=args.as_of, include_history=args.include_history)
    except RetrievalRefused as exc:
        print(f"refused: {exc}")
        return 4
    finally:
        driver.close()
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2, default=str) + "\n")
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    print_triage(report["triage"])
    agent = report["agent"]
    if agent:
        print(f"agent: {agent['framework']} with {agent['model']['provider']}:{agent['model']['name']}; budgets {agent['budgets']}")
        print(f"  tool inventory: {agent.get('tool_inventory')}")
        print(f"  outcome {agent['outcome']} in {agent.get('elapsed_s')} s{'; ' + agent['error'] if agent.get('error') else ''}")
        for call in agent.get("tool_calls", []):
            print(f"  call [{call['scope']}] {call['tool']}({json.dumps(call['args'])}) {call.get('outcome')} {call.get('duration_ms')} ms")
        for refused in agent.get("refused_calls", []):
            print(f"  refused [{refused['scope']}] {refused['tool']}: {refused['reason']}")
        for path in agent.get("graph_paths", []):
            target = path.get("target_policy_id") or path.get("target_name")
            print(f"  path {path['from_section_id']} -{path['edge']}-> {target} ({path['validation_status']})")
        print(f"  evidence chunks: {len(agent.get('evidence_chunk_ids', []))}")
    answer = report["answer"]
    print(f"status: {answer['status']}\nanswer:\n  {answer['answer']}")
    for follow_up in answer.get("follow_up_questions", []):
        print(f"  follow-up: {follow_up}")
    for cite in answer.get("citations", []):
        print(f"  [{cite['citation_id']}] {cite['document_title']} / {cite['section_path']}  resolved {cite['resolved']}")
    return 0 if answer["status"] != "unavailable" else 1


def print_triage(decision: dict) -> None:
    signals = decision["signals"]
    terms = "; ".join(f"{cid}: {', '.join(words)}" for cid, words in signals["distinctive_terms"].items()) or "none"
    if decision["status"] == "needs_clarification":
        print(f"triage: needs clarification, {decision['reason']}")
    else:
        print(f"triage: {decision['route']} in {decision['corpus_id']} ({decision['basis']}); mode {decision['mode']}; "
              f"policies {', '.join(decision['policies']) or 'none named'}")
    print(f"  signals: ids {signals['policy_ids'] or 'none'}; issuers named {signals['named_contexts'] or 'none'}; distinctive terms {terms}")


def format_signals(signals: dict) -> str:
    parts = []
    if "similarity" in signals:
        parts.append(f"vec #{signals['vector_rank']} {signals['similarity']:.4f}")
    if "keyword_rank" in signals:
        terms = f" {','.join(signals['exact_terms'])}" if signals["exact_terms"] else ""
        parts.append(f"bm25 #{signals['keyword_rank']} {signals['bm25']:.2f}+{signals['boost']:.1f}{terms}")
    if "rrf" in signals:
        parts.append(f"rrf {signals['rrf']:.4f}")
    if "rerank_score" in signals:
        parts.append(f"rerank {signals['rerank_score']:.3f} (was #{signals['rank_before_rerank']})")
    for path in signals.get("graph_paths", []):
        section = f" section {path['target_section']}" if path["target_section"] else ""
        how = "added by" if signals["graph_added"] else "also reached by"
        parts.append(f"graph {how} {path['edge']} -> {path['target_policy_id']}{section}")
    return " | ".join(parts)


def print_ask(retrieval: dict, result: dict) -> None:
    search = retrieval["search"]
    check = retrieval["exact_check"]
    print(f"question: {retrieval['question']}")
    print(
        f"snapshot {retrieval['snapshot_id']}  generation {retrieval['index_generation_id']}  as_of {retrieval['as_of']}  "
        f"mode {retrieval['mode']}  k {retrieval['k']}"
    )
    if retrieval["query_input"]:
        print(f"embedder {retrieval['embedder']['model']}@{retrieval['embedder']['revision'][:12]}  query input: {retrieval['query_input']}")
    print(f"search: {search['method']}; {search['eligible']} eligible of {search['generation_chunks']}, {len(search['excluded'])} excluded")
    for stage, detail in search["stages"].items():
        print(f"  {stage}: {detail}")
    grouped: dict[tuple[str, str], int] = {}
    for item in search["excluded"]:
        key = (item["document_version_id"], item["reason"])
        grouped[key] = grouped.get(key, 0) + 1
    for (version_id, reason), count in grouped.items():
        print(f"  excluded {count} chunk(s) of {version_id}: {reason}")
    if check:
        print(f"exact cosine check: top-k agrees {check['top_k_agrees']}, max score gap {check['max_score_gap']:.2e}")
    print("retrieved:")
    for hit in retrieval["hits"]:
        print(
            f"  [{hit['rank']}] {format_signals(hit['signals'])}  "
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
    for follow_up in result.get("follow_up_questions", []):
        print(f"  follow-up: {follow_up}")
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


def run_etl(args: argparse.Namespace) -> int:
    from app.doctor import load_lock
    from app.embedder import embedder_from_lock
    from app.medallion import run_medallion

    report = run_medallion(args.snapshot, embedder_from_lock(load_lock()), profile=args.profile, reason=args.reason)
    print(
        f"bronze {report['bronze_documents']} documents  silver errors {report['silver_errors']}  "
        f"publishable {report['publishable']}"
    )
    print(f"decision: {report['decision']}")
    if report["publishable"]:
        print(f"gold generation {report['generation_id']}  chunks {report['gold_chunks']}")
    else:
        print("gold withheld")
    print(f"zones: {report['output']}")
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["publishable"] else 3


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
