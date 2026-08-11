#!/bin/sh
# run all bash tests; exit nonzero on any failure.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FAIL=0
set -- "$SCRIPT_DIR"/*_test.sh
if [ ! -f "$1" ]; then
  echo "ERROR: no bash tests matched $SCRIPT_DIR/*_test.sh" >&2
  exit 1
fi
for test in "$@"; do
  echo ""
  echo "=== $(basename "$test") ==="
  bash "$test" || FAIL=1
done
echo ""
if [ "$FAIL" = "0" ]; then
  echo "All bash tests passed."
  exit 0
fi
echo "Some bash tests failed."
exit 1
