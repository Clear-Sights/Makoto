#!/bin/sh
# Phase 5.4 smoke test — drives makoto.dispatch end-to-end.
# Success criterion: lazy state init + dispatch event. NOT an audit row: `state/audit.py`
# documents an ONLY-FIRES policy -- one row per Finding-producing invocation -- and the
# benign write below produces no finding, so no row is owed. The original criterion
# predates that policy and asserted one anyway.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRATCH="$(mktemp -d)"
PYTHON_BIN="${MAKOTO_PYTHON:-python3}"
echo "Scratch: $SCRATCH"
echo "Python: $PYTHON_BIN"

# Drive a synthetic PreToolUse event through the dispatcher.
# Lazy init in dispatch.py should create makoto.record.db on first call.
EVENT='{"hook_event_name":"PreToolUse","session_id":"smoke","cwd":"/tmp","tool_input":{"file_path":"/tmp/x.txt","content":"hello"}}'

cd "$REPO_ROOT"
export MAKOTO_STATE_DIR="$SCRATCH/makoto_state"
printf '%s' "$EVENT" | "$PYTHON_BIN" -m makoto.dispatch

# Verify lazy init worked
test -f "$SCRATCH/makoto_state/makoto.record.db" || { echo "FAIL: lazy init didn't create makoto.record.db"; rm -rf "$SCRATCH"; exit 1; }
# Only-fires: a benign event owes no audit row, so an ABSENT or EMPTY audit.jsonl is correct
# here. What must not happen is a row for an event that fired nothing.
if [ -s "$SCRATCH/makoto_state/audit.jsonl" ]; then
  echo "FAIL: audit row written for an event that produced no finding (only-fires policy)"
  rm -rf "$SCRATCH"; exit 1
fi

echo "OK: lazy state init + dispatch; no audit row for a non-firing event (only-fires policy)"
rm -rf "$SCRATCH"
echo "Smoke complete."
