"""Root helper for the topic `textwrap`.

Running from the root, this file shadows the standard library `textwrap`
(sys.path[0] is the script directory). `app/report.py` relies on the stdlib
`textwrap.shorten`, so re-export the stdlib names here first.
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
