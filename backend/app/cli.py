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
    args = parser.parse_args(argv)
    if args.command == "smoke":
        from app.smoke import run_smoke

        report = run_smoke()
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


if __name__ == "__main__":
    raise SystemExit(main())
