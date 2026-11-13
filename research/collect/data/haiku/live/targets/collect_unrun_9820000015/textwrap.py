"""Root helper for the topic `textwrap`.

This file shadows the standard-library `textwrap` when run from the root, so
any attribute not defined here is forwarded to the stdlib module (app/index.py
uses textwrap.shorten).
"""
import importlib.util
import os
import sysconfig


def square_sum(values):
    return sum(v * v for v in values)


_stdlib_path = os.path.join(sysconfig.get_paths()["stdlib"], "textwrap.py")
_spec = importlib.util.spec_from_file_location("_stdlib_textwrap", _stdlib_path)
_stdlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib)


def __getattr__(name):
    return getattr(_stdlib, name)
