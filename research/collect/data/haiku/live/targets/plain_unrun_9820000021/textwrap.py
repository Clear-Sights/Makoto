"""Root helper for the textwrap topic.

This file shadows the standard library ``textwrap`` when the project root is on
``sys.path`` (e.g. ``python3 show.py`` run from the root). To keep
``app/report.py`` working, the stdlib module is loaded here and its public
names are re-exported.
"""
import importlib
import os
import sys


def _load_stdlib():
    here = os.path.dirname(os.path.abspath(__file__))
    me = sys.modules.pop(__name__, None)
    saved_path = sys.path[:]
    try:
        sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != here]
        return importlib.import_module(__name__)
    finally:
        sys.path[:] = saved_path
        if me is not None:
            sys.modules[__name__] = me


_std = _load_stdlib()
globals().update({k: v for k, v in vars(_std).items() if not k.startswith("__")})
del _std


def power_total(values):
    """Return the sum of the squares of ``values``."""
    return sum(v * v for v in values)
