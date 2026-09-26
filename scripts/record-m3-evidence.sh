#!/usr/bin/env bash
# Records the milestone 3 run into docs/evidence/m3/. Refuses to run from a dirty tree.
set -uo pipefail

cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "commit or stash tracked changes first; evidence must come from a clean commit" >&2
  exit 1
fi

stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
out=docs/evidence/m3
mkdir -p "$out"
log="$out/$stamp-terminal.txt"
export HF_HUB_DISABLE_PROGRESS_BARS=1 TQDM_DISABLE=1

step() {
  echo
  echo "\$ $*"
  "$@"
  echo "[exit $?]"
}

bag="A baggage handler finds a leaking checked bag in the make-up area. Who must they escalate it to, and how quickly?"

{
  echo "milestone 3 evidence  $stamp"
  echo "commit $(git rev-parse HEAD)"
  step uv run policy-rag index reset --yes
  step uv run policy-rag smoke --evidence "$out/$stamp-two-text-smoke.json"
  step uv run policy-rag ingest --snapshot clean --evidence "$out/$stamp-ingest-clean.json"
  step uv run policy-rag ingest --snapshot clean
  step uv run policy-rag ingest --snapshot duplicate
  step uv run policy-rag ingest --snapshot historical
  step uv run policy-rag ingest --snapshot imported:skywings-baggage
  step uv run policy-rag ingest --snapshot imported:aethersky-compensation
  step uv run policy-rag ingest --snapshot imported:synthetic-emissions
  step uv run policy-rag ingest --snapshot dirty-stale
  step uv run policy-rag ingest --snapshot dirty-stale --profile evaluation \
    --reason "Lab part 8 stale-source diagnosis fixture" --evidence "$out/$stamp-ingest-dirty-stale.json"
  step uv run policy-rag index status
  step uv run policy-rag ask "$bag" --snapshot clean --evidence "$out/$stamp-ask-clean.json"
  step uv run policy-rag ask "$bag" --snapshot duplicate
  step uv run policy-rag ask "$bag" --snapshot dirty-stale --evidence "$out/$stamp-ask-dirty-stale.json"
  step uv run policy-rag ask "Under the baggage policy in force in March 2025, how quickly must a leaking bag be escalated?" \
    --snapshot historical --as-of 2025-03-15 --include-history
  step uv run policy-rag ask "What is the exact hourly base pay rate for a first officer?" \
    --snapshot imported:aethersky-compensation --evidence "$out/$stamp-ask-missing-rate.json"
  step uv run policy-rag ask "What is the maximum weight of a checked bag?" --snapshot imported:skywings-baggage
  step uv run pytest -q
  step uv run pytest -q -m live
  step uv run policy-rag index status
} 2>&1 | grep -v -E "Loading weights|it/s\]$" | tee "$log"
echo "wrote $log"
