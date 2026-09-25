#!/usr/bin/env bash
# Records a milestone 4 run into docs/evidence/m4/. Refuses to run from a dirty tree.
#   dev      hybrid demonstration in every mode, then the dev suite
#   heldout  the frozen held-out suite, then the live tests (which include held-out generated cases)
set -uo pipefail

cd "$(dirname "$0")/.."
suite=${1:-}
if [ "$suite" != dev ] && [ "$suite" != heldout ]; then
  echo "usage: $0 dev|heldout" >&2
  exit 2
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "commit or stash tracked changes first; evidence must come from a clean commit" >&2
  exit 1
fi

stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
out=docs/evidence/m4
mkdir -p "$out"
log="$out/$stamp-$suite-terminal.txt"
export HF_HUB_DISABLE_PROGRESS_BARS=1 TQDM_DISABLE=1

step() {
  echo
  echo "\$ $*"
  "$@"
  echo "[exit $?]"
}

demo="What does AP-SEC-003 section 2 say?"

{
  echo "milestone 4 evidence ($suite)  $stamp"
  echo "commit $(git rev-parse HEAD)"
  step uv run policy-rag index status
  if [ "$suite" = dev ]; then
    for mode in vector keyword hybrid hybrid_rerank; do
      step uv run policy-rag ask "$demo" --snapshot clean --mode "$mode" --evidence "$out/$stamp-demo-$mode.json"
    done
    step uv run policy-rag evaluate --suite dev --evidence "$out/$stamp-dev-evaluation.json"
    step uv run pytest -q
  else
    step uv run policy-rag evaluate --suite heldout --evidence "$out/$stamp-heldout-evaluation.json"
    step uv run pytest -q -m live
  fi
} 2>&1 | grep -v -E "Loading weights|it/s\]$" | tee "$log"
echo "wrote $log"
