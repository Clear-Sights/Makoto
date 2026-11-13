"""Root helper for the statistics topic.

This file shadows the standard library ``statistics`` module when the
project root is on ``sys.path``. ``app/feed.py`` depends on the stdlib
``mean``, so the stdlib module is loaded from its file and its public
names are re-exported here.
"""
import importlib.util
import os
import sysconfig

_stdlib_path = os.path.join(sysconfig.get_path("stdlib"), "statistics.py")
_spec = importlib.util.spec_from_file_location("_stdlib_statistics", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)

globals().update(
    {k: v for k, v in vars(_stdlib).items() if not k.startswith("__")}
)


def total_squares(values):
    return sum(v * v for v in values)
