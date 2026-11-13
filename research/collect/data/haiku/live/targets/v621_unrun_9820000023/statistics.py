"""Root helper for the statistics topic.

This file shadows the standard library `statistics` module whenever the
project root is on sys.path (e.g. `python3 show.py`). app/store.py uses the
stdlib `mean`, so the stdlib module is loaded from its own file and its
public names are re-exported here.
"""
import importlib.util
import os
import sysconfig

_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "statistics.py")
_spec = importlib.util.spec_from_file_location("_stdlib_statistics", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)
globals().update({name: getattr(_stdlib, name) for name in _stdlib.__all__})


def power_total(values):
    return sum(v * v for v in values)
