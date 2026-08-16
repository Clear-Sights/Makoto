#!/bin/sh
# Phase 5.4 smoke test — drives makoto._dispatch end-to-end.
# Spec §6 success criterion: lazy state init + dispatch event + audit row written.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRATCH="$(mktemp -d)"
PYTHON_BIN="${MAKOTO_PYTHON:-python3}"
echo "Scratch: $SCRATCH"
echo "Python: $PYTHON_BIN"

# Drive a synthetic PreToolUse event through the dispatcher.
# Lazy init in _dispatch.py should create makoto.db on first call.
EVENT='{"hook_event_name":"PreToolUse","session_id":"smoke","cwd":"/tmp","tool_input":{"file_path":"/tmp/x.txt","content":"hello"}}'

cd "$REPO_ROOT"
export MAKOTO_STATE_DIR="$SCRATCH/makoto_state"
printf '%s' "$EVENT" | "$PYTHON_BIN" -m makoto._dispatch

# Verify lazy init worked
test -f "$SCRATCH/makoto_state/makoto.db" || { echo "FAIL: lazy init didn't create makoto.db"; rm -rf "$SCRATCH"; exit 1; }
test -f "$SCRATCH/makoto_state/audit.jsonl" || { echo "FAIL: audit.jsonl missing"; rm -rf "$SCRATCH"; exit 1; }

echo "OK: lazy state init + dispatch wrote audit.jsonl"
rm -rf "$SCRATCH"
echo "Smoke complete."
