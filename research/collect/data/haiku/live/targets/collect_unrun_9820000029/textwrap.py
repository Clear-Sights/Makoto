import importlib.util
import os
import sysconfig

# A root-level textwrap.py shadows the standard library module, and app/util.py
# relies on textwrap.shorten. Load the stdlib copy by path and re-export it so
# existing callers keep working.
_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "textwrap.py")
_spec = importlib.util.spec_from_file_location("_stdlib_textwrap", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)
globals().update({k: v for k, v in vars(_stdlib).items() if not k.startswith("__")})


def power_total(values):
    return sum(v * v for v in values)
