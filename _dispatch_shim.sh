#!/bin/sh
# Makoto dispatch shim — exec the Python hot path.
# MAKOTO_PYTHON env var picks the python interpreter; defaults to python3.
PYTHON_BIN="${MAKOTO_PYTHON:-python3}"
exec "$PYTHON_BIN" -m makoto._dispatch
