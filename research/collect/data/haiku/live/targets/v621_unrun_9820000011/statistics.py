"""Root helper for the statistics topic.

This file shadows the standard library's ``statistics`` module when the
project root is on sys.path (e.g. ``python3 show.py`` run from the root).
To keep ``app/feed.py`` working, the stdlib module is loaded by path and its
public names are re-exported here before ``total_squares`` is defined.
"""
import importlib.util
import os
import sysconfig


def _load_stdlib_statistics():
    path = os.path.join(sysconfig.get_paths()["stdlib"], "statistics.py")
    spec = importlib.util.spec_from_file_location("_stdlib_statistics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stdlib = _load_stdlib_statistics()
for _name in dir(_stdlib):
    if not _name.startswith("_"):
        globals().setdefault(_name, getattr(_stdlib, _name))


def total_squares(values):
    """Return the sum of the squares of ``values``."""
    return sum(v * v for v in values)
