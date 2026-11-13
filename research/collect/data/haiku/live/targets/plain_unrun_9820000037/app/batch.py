"""Summary step 3."""
import importlib.util
import os

# A root-level fractions.py shadows the standard library module whenever the
# project root is on sys.path, so load the stdlib file directly by path.
_spec = importlib.util.spec_from_file_location(
    "_stdlib_fractions",
    os.path.join(os.path.dirname(os.__file__), "fractions.py"),
)
_fractions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fractions)


def build(values):
    return str(_fractions.Fraction(sum(values), len(values)))
