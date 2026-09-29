#!/bin/sh
# Makoto's done line as one command, no model call: every planted fault caught and every
# look-alike silent on the mesh (tonight's false fires included), each check's width stated and
# current, every recorded lesson's planted repeat caught, and each hook call instantaneous.
set -e
cd "$(dirname "$0")/.."
MAKOTO_ROOT=plugin python3 tools/mesh/mesh.py > /tmp/makoto-done-mesh.txt
tail -1 /tmp/makoto-done-mesh.txt
grep -q ' distance 0$' /tmp/makoto-done-mesh.txt
python3 tools/cover.py --check
if awk -F'\t' 'NR>1 && $5!="measured"' docs/COVERAGE.tsv | grep -q .; then echo "a check's width is not measured"; exit 1; fi
PYTHONPATH=plugin python3 -m pytest -q -p no:cacheprovider tests/test_round_nine.py tests/test_hook_latency.py
echo "MAKOTO DONE"
