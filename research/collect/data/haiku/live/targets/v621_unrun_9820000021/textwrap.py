"""Root helper for the topic `textwrap`.

This file shadows the standard library `textwrap` when run from the root
directory, so the stdlib module is loaded from its real path and its public
names are re-exported to keep `app/report.py` working.
"""
import importlib.util as _importlib_util
import os as _os
import sysconfig as _sysconfig

_stdlib_path = _os.path.join(_sysconfig.get_paths()["stdlib"], "textwrap.py")
_spec = _importlib_util.spec_from_file_location("_stdlib_textwrap", _stdlib_path)
_stdlib = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)
globals().update({k: v for k, v in vars(_stdlib).items() if not k.startswith("__")})


def power_total(values):
    return sum(v * v for v in values)
