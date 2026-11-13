"""Root helper for the textwrap topic.

This file shadows the standard library's ``textwrap`` when run from the root,
so the stdlib module is loaded by path and its public names are re-exported
for code (e.g. app/util.py) that expects them.
"""
import importlib.util
import os
import sysconfig

_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "textwrap.py")
_spec = importlib.util.spec_from_file_location("_stdlib_textwrap", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)

shorten = _stdlib.shorten
wrap = _stdlib.wrap
fill = _stdlib.fill
dedent = _stdlib.dedent
indent = _stdlib.indent


def power_total(values):
    """Return the sum of the squares of ``values``."""
    return sum(v * v for v in values)
