#!/usr/bin/env bash
# Records the milestone 5 run into docs/evidence/m5/. Refuses to run from a dirty tree.
# Triage outcomes, the multi-policy scenario in graph_rerank, hybrid_rerank, and agent
# mode, the dev suite in every mode, and the full live and unit test suites.
set -uo pipefail

cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "commit or stash tracked changes first; evidence must come from a clean commit" >&2
  exit 1
fi

stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
out=docs/evidence/m5
mkdir -p "$out"
log="$out/$stamp-terminal.txt"
export HF_HUB_DISABLE_PROGRESS_BARS=1 TQDM_DISABLE=1

step() {
  echo
  echo "\$ $*"
  "$@"
  echo "[exit $?]"
}

multi="To whom is an operational incident first reported, and where does the incident policy send staff for baggage escalation procedures?"
restricted="A handler finds a restricted item in a checked bag. What must happen to the bag, who approves the item, and how must the incident be reported?"

{
  echo "milestone 5 evidence  $stamp"
  echo "commit $(git rev-parse HEAD)"
  step uv run policy-rag index status
  step uv run policy-rag ask "What is the checked bag weight limit?"
  step uv run policy-rag ask "Under AP-BAG-001, what does SkyWings charge for overweight bags?"
  step uv run policy-rag ask "What is the SkyWings checked baggage allowance?"
  step uv run policy-rag ask "$multi" --snapshot clean --mode hybrid_rerank --evidence "$out/$stamp-multi-hybrid_rerank.json"
  step uv run policy-rag ask "$multi" --snapshot clean --evidence "$out/$stamp-multi-triaged.json"
  step uv run policy-rag agent "$multi" --snapshot clean --evidence "$out/$stamp-multi-agent.json"
  step uv run policy-rag agent "$restricted" --evidence "$out/$stamp-restricted-agent.json"
  step uv run policy-rag evaluate --suite dev --evidence "$out/$stamp-dev-evaluation.json"
  step uv run pytest -q -m live --junitxml "$out/$stamp-live-junit.xml"
  step uv run python scripts/check_no_skips.py "$out/$stamp-live-junit.xml"
  step uv run pytest -q
} 2>&1 | grep -v -E "Loading weights|it/s\]$" | tee "$log"
echo "wrote $log"
