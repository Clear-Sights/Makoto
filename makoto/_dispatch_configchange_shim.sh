#!/bin/sh
# ConfigChange companion to _dispatch_shim.sh.  Pin the import root to the live plugin root so a
# project-local makoto/ directory cannot shadow the packaged adapter at hook-fire time.
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || ! cd "$CLAUDE_PLUGIN_ROOT" 2>/dev/null; then
  echo "makoto configchange shim: CLAUDE_PLUGIN_ROOT unset or not a directory -- failing open" >&2
  exit 0
fi
PYTHON_BIN="${MAKOTO_PYTHON:-python3}"
exec "$PYTHON_BIN" -m makoto._dispatch_configchange
