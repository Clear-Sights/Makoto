"""Root helper for the topic `textwrap`.

This file shadows the standard library's `textwrap` when run from the root,
so it loads the stdlib module by path and re-exports its public names. This
keeps `app/util.py` (which calls `textwrap.shorten`) working unchanged.
"""
import importlib.util
import os
import sysconfig

_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "textwrap.py")
_spec = importlib.util.spec_from_file_location("_stdlib_textwrap", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)

globals().update({k: v for k, v in vars(_stdlib).items() if not k.startswith("__")})


def power_total(values):
    return sum(v * v for v in values)
