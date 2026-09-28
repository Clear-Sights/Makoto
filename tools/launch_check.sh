#!/bin/sh
# Makoto launch checklist: every item PASS or FAIL, exit 0 only when all pass.
# usage: sh tools/launch_check.sh [--suite]      (--suite also runs the full test suite, ~1 min)
# Each FAIL line names the one act that clears it. Nothing here edits anything.
cd "$(dirname "$0")/.." || exit 2
fails=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n      -> %s\n' "$1" "$2"; fails=$((fails + 1)); }

PY="${MAKOTO_PYTHON:-python3}"
if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  pass "python >= 3.11 ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"
else
  fail "python >= 3.11" "install Python 3.11+ or set MAKOTO_PYTHON"
fi
if "$PY" -c 'import pytest' 2>/dev/null; then pass "pytest importable"
else fail "pytest importable" "$PY -m pip install pytest (or set MAKOTO_PYTHON to a venv that has it)"; fi

git fetch -q origin main 2>/dev/null
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main 2>/dev/null)" ]; then pass "checkout is origin/main ($(git rev-parse --short HEAD))"
else fail "checkout is origin/main" "git checkout main && git pull --ff-only origin main (or work on a branch from it)"; fi
if [ -z "$(git status --porcelain)" ]; then pass "tree clean"; else fail "tree clean" "commit or stash the changes shown by git status"; fi

for law in "render_checks.py --check" register_map.py merge_pass.py; do
  if "$PY" tools/$law >/dev/null 2>&1; then pass "law $law"; else fail "law $law" "run $PY tools/$law and fix what it prints"; fi
done

want="$("$PY" -c 'import json; print(json.load(open("plugin/.claude-plugin/plugin.json"))["version"])')"
found=0
for inst in "$HOME"/.claude/plugins/synced/*/makoto "$HOME"/.claude/plugins/cache/*/makoto/*; do
  [ -f "$inst/.claude-plugin/plugin.json" ] || continue
  found=1
  have="$("$PY" -c "import json; print(json.load(open('$inst/.claude-plugin/plugin.json'))['version'])")"
  if [ "$have" = "$want" ] && diff -rq --exclude=__pycache__ plugin "$inst" >/dev/null 2>&1; then
    pass "installed copy $inst is this checkout ($have)"
  else
    fail "installed copy $inst is this checkout (installed $have, repo $want)" \
      "reinstall Makoto from the marketplace (Settings > Plugins, or claude plugin update makoto), then start a NEW session: hooks load at session start"
  fi
done
[ "$found" = 1 ] || fail "Makoto installed for this account" "install the Makoto plugin from https://github.com/Clear-Sights/Makoto, then start a new session"

if [ "${1:-}" = "--suite" ]; then
  if PYTHONPATH="$PWD/plugin" "$PY" -m pytest -q -p no:cacheprovider >/dev/null 2>&1; then pass "suite green"
  else fail "suite green" "PYTHONPATH=\$PWD/plugin $PY -m pytest -q -p no:cacheprovider"; fi
fi

if [ "$fails" = 0 ]; then echo "LAUNCH: every item passes"; exit 0; fi
echo "LAUNCH: $fails item(s) fail"; exit 1
