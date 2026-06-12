"""stopchecks package: live Stop gates discovered from stopcheck_*.py."""
from __future__ import annotations
import importlib
import pkgutil
from functools import lru_cache
from makoto.stopchecks._types import StopCheck, GateContext  # re-exported package API

__all__ = ["StopCheck", "GateContext", "load_stopchecks"]


@lru_cache(maxsize=1)
def load_stopchecks():
    """Every live gate: import each stopchecks/stopcheck_*.py, collect its GATE export, sorted by id.
    Memoized so the Stop hot-path never filesystem-scans per event."""
    import makoto.stopchecks as pkg
    out = []
    for mi in sorted(m.name for m in pkgutil.iter_modules(pkg.__path__)
                     if m.name.startswith("stopcheck_")):
        mod = importlib.import_module(f"makoto.stopchecks.{mi}")
        g = getattr(mod, "GATE", None)
        if g is not None:
            out.append(g)
    return sorted(out, key=lambda g: g.id)
