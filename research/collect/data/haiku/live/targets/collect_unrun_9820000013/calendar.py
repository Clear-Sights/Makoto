import importlib.util
import os
import sys
import sysconfig


def square_sum(values):
    return sum(v * v for v in values)


# This file shadows the stdlib `calendar` module whenever the project root is
# on sys.path (e.g. `python3 show.py` run from the root). app/feed.py relies on
# stdlib `calendar.monthrange`, so load the stdlib module by path under a
# private name and re-export its public names here.
_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "calendar.py")
_spec = importlib.util.spec_from_file_location("_stdlib_calendar", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _stdlib
_spec.loader.exec_module(_stdlib)

for _name in _stdlib.__all__:
    globals()[_name] = getattr(_stdlib, _name)
