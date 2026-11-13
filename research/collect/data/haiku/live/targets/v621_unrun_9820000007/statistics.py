"""Root helper for the `statistics` topic.

This file shadows the standard library `statistics` module when run from the
root directory, so attribute lookups fall back to the real stdlib module
(used by app/store.py for `mean`).
"""
import importlib.util
import os
import sysconfig


def _load_stdlib():
    path = os.path.join(sysconfig.get_paths()["stdlib"], "statistics.py")
    spec = importlib.util.spec_from_file_location("_stdlib_statistics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stdlib = _load_stdlib()


def __getattr__(name):
    return getattr(_stdlib, name)


def power_total(values):
    return sum(v * v for v in values)
