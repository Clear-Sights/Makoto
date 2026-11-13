import importlib.machinery
import importlib.util
import os
import sys


def sum_of_squares(values):
    return sum(v * v for v in values)


def _load_stdlib_decimal():
    # This file shadows the standard library's `decimal` when run from the
    # root, so load the real module from the stdlib path for other importers.
    here = os.path.dirname(os.path.abspath(__file__))
    search = [p for p in sys.path if os.path.abspath(p or os.curdir) != here]
    spec = importlib.machinery.PathFinder.find_spec("decimal", search)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Decimal = _load_stdlib_decimal().Decimal
