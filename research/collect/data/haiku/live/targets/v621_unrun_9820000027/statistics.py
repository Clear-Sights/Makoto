import importlib.util
import os
import sysconfig


def total_squares(values):
    return sum(v * v for v in values)


# This file shadows the standard library's `statistics` module when the root
# is on sys.path (e.g. app/feed.py does `import statistics` and calls `mean`).
# Load the stdlib module by path and re-export its public names so that code
# keeps working.
_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "statistics.py")
_spec = importlib.util.spec_from_file_location("_stdlib_statistics", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)

for _name in getattr(_stdlib, "__all__", []):
    globals().setdefault(_name, getattr(_stdlib, _name))
