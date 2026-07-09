"""FP-measurement runner for the gate.hollowTest Stop gate (formerly gate.hollow_test).

`measure(paths)` runs the real `analyze_file` over each path and returns the total fire count plus
the per-fire detail. It is the same analyzer the live Stop hook fires, so the count it reports is the
analyzer's actual false-positive surface over the corpus — no separate, weaker re-implementation.
Mirrors `_fpHarness.py` (gate.deadPureStatement's equivalent runner).

Test-support tooling only (see `makoto/tests/test_hollow_test_fp.py`) — not imported by any live
dispatch/gate code, so it lives as a flat `_`-prefixed file (package plumbing, never a detector
module; `checks._loader`'s scan skips it) rather than needing its own CHECK export.
"""
from __future__ import annotations
from pathlib import Path

from makoto.checks.hollowTest import analyze_file


def measure(paths) -> dict:
    fires = []
    for p in paths:
        try:
            src = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        fires.extend(analyze_file(src, str(p)))
    return {"fires": len(fires), "detail": fires}
