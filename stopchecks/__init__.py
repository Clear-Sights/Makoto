"""stopchecks package: live Stop gates, now DISCOVERED from the flat `makoto/checks/` package
(SPEC-5 Task 4, owner-revised layout) rather than this package's own directory.

The 11 stop-gate modules (formerly `stopchecks/stopcheck_*.py` + their engines) moved to
`makoto/checks/` with descriptive names (see `makoto.checks._declared.DECLARED_IDS` for the
id->filename map); their `.id`/`.run(ctx)` contract and the `StopCheck`/`GateContext` schemas are
UNCHANGED. This module keeps `load_stopchecks()`'s public contract (memoized, sorted-by-id list of
`StopCheck` `GATE` exports) working for every existing caller (`_dispatch.py`, and the many tests
that still `from makoto.stopchecks import load_stopchecks` / `GateContext` / `StopCheck`) by
routing its discovery through `makoto.checks._loader`'s own flat-file-candidate convention instead
of the old `pkgutil.iter_modules` scan over this package's (now near-empty) directory -- ripping
this loader out entirely in favor of `checks._loader.load_checks(edge="Stop")` is Task 8's job,
not this one's (Task 4 must keep both discovery paths live side by side)."""
from __future__ import annotations
import importlib
from functools import lru_cache

from makoto.checks._shared import StopCheck, GateContext  # re-exported package API
from makoto.checks import _loader as _cl

__all__ = ["StopCheck", "GateContext", "load_stopchecks"]


@lru_cache(maxsize=1)
def load_stopchecks():
    """Every live gate: import each non-underscore-prefixed module directly under `makoto/checks/`
    (the same flat-file convention `checks._loader.load_checks` uses) and collect its `GATE`
    export (a `StopCheck`, distinct from that module's ALSO-exported `CHECK` used by
    `load_checks`). Memoized so the Stop hot-path never filesystem-scans per event."""
    out = []
    for path in _cl._candidate_files(_cl._PACKAGE_DIR):
        mod = importlib.import_module(f"makoto.checks.{path.stem}")
        g = getattr(mod, "GATE", None)
        if g is not None:
            out.append(g)
    return sorted(out, key=lambda g: g.id)
