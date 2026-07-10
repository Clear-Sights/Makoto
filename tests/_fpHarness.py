"""FP-measurement runner, shared by gate.deadPureStatement (formerly gate.liveness) and
gate.hollowTest (formerly gate.hollow_test) -- previously two byte-near-identical files
(`_fpHarness.py`/`_hollowTestFpHarness.py`, found alpha-equivalent by AST canonicalization,
2026-07-09), merged into one parameterized runner rather than left as twins.

`measure(paths, analyzer)` runs the real `analyzer.analyze_file` over each path and returns the
total fire count plus the per-fire detail. It is the same analyzer the live Stop hook fires, so the
count it reports is the analyzer's actual false-positive surface over the corpus -- no separate,
weaker re-implementation.

Test-support tooling only (see `tests/test_liveness_fp.py`, `tests/test_hollow_test_fp.py`) -- not
imported by any live dispatch/gate code, so it lives HERE in `tests/` (bedrock audit, 2026-07-10:
its former home in `substrate/` misrepresented it as production plumbing; a module consumed only
by tests belongs with the tests that consume it).
"""
from __future__ import annotations
from pathlib import Path


def measure(paths, analyzer) -> dict:
    fires = []
    for p in paths:
        try:
            src = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        fires.extend(analyzer.analyze_file(src, str(p)))
    return {"fires": len(fires), "detail": fires}
