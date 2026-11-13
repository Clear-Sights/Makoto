"""Root helper for the `decimal` topic.

Because this file is at the project root, it shadows the standard library's
`decimal` module for anything run from here (app/cache.py imports it). So the
real stdlib module is loaded by path and its public names are re-exported.
"""
import importlib.util
import os
import sysconfig

_stdlib_path = os.path.join(sysconfig.get_path("stdlib"), "decimal.py")
_spec = importlib.util.spec_from_file_location("_stdlib_decimal", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)

for _name, _value in vars(_stdlib).items():
    if _name == "__all__" or not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value


def sum_of_squares(values):
    return sum(v * v for v in values)
