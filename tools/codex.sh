#!/bin/sh
# Codex login for this session. The auth JSON comes from $CODEX_AUTH_JSON (set once in the
# environment settings), never from a repository: auth.json is gitignored and stays mode 600.
command -v codex >/dev/null || { echo "LAUNCH MISSING codex: install it (npm i -g @openai/codex), then start a new session"; exit 2; }
codex login status >/dev/null 2>&1 && { echo "codex logged in"; exit 0; }
[ -n "$CODEX_AUTH_JSON" ] || { echo "LAUNCH MISSING codex login: set CODEX_AUTH_JSON to the contents of ~/.codex/auth.json in the environment settings, then start a new session"; exit 2; }
d="${CODEX_HOME:-$HOME/.codex}"; mkdir -p "$d"
(umask 077; printf '%s\n' "$CODEX_AUTH_JSON" > "$d/auth.json") && chmod 600 "$d/auth.json"
codex login status >/dev/null 2>&1 && { echo "codex logged in"; exit 0; }
echo "LAUNCH MISSING codex login: CODEX_AUTH_JSON is set but codex still reports not logged in; refresh it from a fresh ~/.codex/auth.json"; exit 2
