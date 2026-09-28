#!/bin/sh
# Makoto launch checklist: every item PASS or FAIL, exit 0 only when all pass.
# usage: sh tools/launch_check.sh [--suite]
# Launch runs it bare (~7 s). --suite adds the full test suite (~76 s): run that before calling a
# step done, never at launch, where main's merge has already run it.
# Each FAIL line names the one act that clears it. Nothing here edits anything.
cd "$(dirname "$0")/.." || exit 2
fails=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n      -> %s\n' "$1" "$2"; fails=$((fails + 1)); }
# A NOTE is an act only Gabriel can take (a plugin install lands next session): shown, never red.
note() { printf 'NOTE  %s\n      -> %s\n' "$1" "$2"; }

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
# Name the copy whose hooks run this session and every leftover beside it (tools/makoto_copies.py
# reads the files Claude Code reads to pick it). Reinstalling or removing a copy is Gabriel's act.
copies="$("$PY" tools/makoto_copies.py "$HOME")"
live="$(printf '%s\n' "$copies" | grep -c '^live' || true)"
tab="$(printf '\t')"
printf '%s\n' "$copies" | while IFS="$tab" read -r state inst have why; do
  [ -n "$state" ] || continue
  if [ "$state" = unused ]; then
    note "unused Makoto copy $inst ($have): its hooks do not load ($why)" \
      "remove it: claude plugin uninstall for a marketplace copy, or delete the directory"
  elif [ "$have" = "$want" ] && diff -rq --exclude=__pycache__ plugin "$inst" >/dev/null 2>&1; then
    pass "live Makoto copy $inst is this checkout ($have; $why)"
  else
    note "live Makoto copy $inst is $have, repo is $want: its hooks run this session ($why)" \
      "reinstall Makoto from the marketplace (Settings > Plugins, or claude plugin update makoto), then start a NEW session: hooks load at session start"
  fi
done
[ "$live" -gt 1 ] && note "$live Makoto copies are live: every hook runs $live times" \
  "keep the account-synced copy and claude plugin uninstall the marketplace one, then start a NEW session"
[ "$live" = 0 ] && note "no installed Makoto copy loads for this account" "install the Makoto plugin from https://github.com/Clear-Sights/Makoto (or enable it in Settings > Plugins), then start a NEW session"

# DetIO is on in every handoff's launch: its hooks cut the tokens this work reads. Read the
# installed copy's own version line; the act that clears a miss is the install, then a new session.
detio="" dver=""
for inst in "$HOME"/.claude/plugins/synced/*/detio "$HOME"/.claude/plugins/cache/*/detio/*; do
  [ -f "$inst/.claude-plugin/plugin.json" ] || continue
  v="$("$PY" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$inst/.claude-plugin/plugin.json" 2>/dev/null)"
  [ -n "$v" ] && { detio="$inst"; dver="$v"; break; }
done
if [ -n "$dver" ]; then
  pass "DetIO installed ($dver at $detio)"
else
  fail "DetIO installed" "claude plugin marketplace add Clear-Sights/DetIO && claude plugin install detio@detio, then start a NEW session"
fi

if sout="$(sh tools/scour.sh 2>&1)"; then pass "scour at its pin ($(printf '%s\n' "$sout" | grep '^SCOUR entries=' | head -1))"
else fail "scour at its pin" "$(printf '%s\n' "$sout" | grep '^LAUNCH MISSING' | head -1)"; fi

for skill in cheap-execution adversarial-review; do
  hit=""; for f in "$HOME"/.claude/skills/"$skill"/SKILL.md "$HOME"/.claude/skills/*/*/"$skill"/SKILL.md; do [ -f "$f" ] && hit="$f"; done
  if [ -n "$hit" ]; then pass "skill $skill loaded"
  else fail "skill $skill loaded" "enable the $skill skill for this account (claude.ai Settings > Capabilities > Skills), then start a NEW session"; fi
done

if [ "${1:-}" = "--suite" ]; then
  if PYTHONPATH="$PWD/plugin" "$PY" -m pytest -q -p no:cacheprovider >/dev/null 2>&1; then pass "suite green"
  else fail "suite green" "PYTHONPATH=\$PWD/plugin $PY -m pytest -q -p no:cacheprovider"; fi
fi

if [ "$fails" = 0 ]; then echo "LAUNCH: every item passes"; exit 0; fi
echo "LAUNCH: $fails item(s) fail"; exit 1
