#!/bin/sh
# Makoto dispatch shim — exec the Python hot path from the plugin root.
# cd-pinned: `python3 -m` puts its cwd FIRST on sys.path, so without the pin a stray makoto/
# directory in the session's working tree shadows the plugin package and every hook dies with
# ModuleNotFoundError exit 1 (observed live as a 100% hook-failure rate on the marketplace
# install; repro pinned by tests/test_dispatch_shim.py). Running from the plugin root makes the
# plugin's own package the first candidate. Failure direction when the plugin root itself is
# unusable matches _dispatch's own HYBRID fail-open: guaranteed-loud stderr, empty envelope,
# exit 0 — a broken install must never wedge the harness.
# NB: a bare `cd ""` succeeds in sh, so the empty/unset case needs its own test.
# MAKOTO_PYTHON env var picks the python interpreter; defaults to python3.
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || ! cd "$CLAUDE_PLUGIN_ROOT" 2>/dev/null; then
  echo "makoto _dispatch_shim: CLAUDE_PLUGIN_ROOT unset or not a directory -- failing open" >&2
  printf '%s' '{}'
  exit 0
fi
PYTHON_BIN="${MAKOTO_PYTHON:-python3}"
exec "$PYTHON_BIN" -m makoto._dispatch
