"""Root helper for the `statistics` topic.

This file shadows the standard library `statistics` module whenever the
project root is first on sys.path (e.g. `python3 show.py`). app/store.py
depends on `statistics.mean`, so any attribute not defined here is forwarded
to the real stdlib module.
"""
import os

_stdlib = None


def power_total(values):
    return sum(v * v for v in values)


def __getattr__(name):
    global _stdlib
    if _stdlib is None:
        import importlib.util

        path = os.path.join(os.path.dirname(os.__file__), "statistics.py")
        spec = importlib.util.spec_from_file_location("_stdlib_statistics", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _stdlib = module
    return getattr(_stdlib, name)
