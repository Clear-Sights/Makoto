"""Root helper for the `fractions` topic.

This file shadows the standard-library `fractions` module when the root is on
sys.path (e.g. `python3 show.py`). `app/index.py` relies on the stdlib
`fractions.Fraction`, so load the stdlib module from its file and re-export
its public names before adding our own helpers.
"""
import importlib.util
import os
import sysconfig

_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "fractions.py")
_spec = importlib.util.spec_from_file_location("_stdlib_fractions", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)

for _name, _value in vars(_stdlib).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


def sum_of_squares(values):
    """Return the sum of the squares of ``values``."""
    return sum(v * v for v in values)
