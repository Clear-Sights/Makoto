"""Summary step 3."""
import importlib.util
import os
import sysconfig

# The root-level helper module is named statistics.py, which shadows the
# standard library module of the same name when running from the root.
# Load the standard library copy explicitly by its file path.
_spec = importlib.util.spec_from_file_location(
    "_stdlib_statistics",
    os.path.join(sysconfig.get_paths()["stdlib"], "statistics.py"),
)
_stdlib_statistics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib_statistics)


def build(values):
    return str(_stdlib_statistics.mean(values))
