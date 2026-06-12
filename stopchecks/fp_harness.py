"""FP-measurement runner for the liveness Stop gate.

`measure(paths)` runs the real `analyze_file` over each path and returns the total fire count plus
the per-fire detail. It is the same analyzer the live Stop hook fires, so the count it reports is the
analyzer's actual false-positive surface over the corpus — no separate, weaker re-implementation.
"""
from __future__ import annotations
from pathlib import Path

from makoto.stopchecks.liveness import analyze_file


def measure(paths) -> dict:
    fires = []
    for p in paths:
        try:
            src = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        fires.extend(analyze_file(src, str(p)))
    return {"fires": len(fires), "detail": fires}
