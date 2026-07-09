"""Enforces the import-graph-isolation invariant for the two detector engines that deliberately
stay dependency-free from mutable Makoto substrate: `deadPureStatement.py` and `hollowTest.py`.

2026-07-09: this property was previously only a docstring claim ("stays stdlib-only/self-
contained"). The owner correctly rejected treating that claim as sufficient justification on its
own -- a claim of intent is not proof the intent holds. This test makes the property fail loudly
the moment it stops being true, instead of resting on an assertion.

`substrate/_stdlib_ast_helpers.py` is the one whitelisted shared import both engines may use --
it exists specifically so the isolation property is real without duplicating the shared helper
functions across both files.
"""
from __future__ import annotations

import ast
from pathlib import Path

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "checks"
_SUBSTRATE_DIR = Path(__file__).resolve().parent.parent / "substrate"
_ALLOWED_STDLIB = {"ast", "os", "tempfile", "pathlib", "__future__"}
_ALLOWED_MAKOTO = {"makoto.substrate._shared", "makoto.substrate._stdlib_ast_helpers", "makoto.core.schema",
                   "makoto.substrate._loader"}


def _imported_modules(path: Path) -> set:
    tree = ast.parse(path.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def _assert_isolated(filename: str) -> None:
    mods = _imported_modules(_CHECKS_DIR / filename)
    offenders = {m for m in mods
                 if m not in _ALLOWED_STDLIB and m not in _ALLOWED_MAKOTO}
    assert not offenders, (
        f"{filename} imports outside its stdlib+whitelisted-helper isolation contract: {offenders}")


def test_dead_pure_statement_is_stdlib_isolated():
    _assert_isolated("deadPureStatement.py")


def test_hollow_test_is_stdlib_isolated():
    _assert_isolated("hollowTest.py")


def test_stdlib_ast_helpers_itself_is_stdlib_only():
    mods = _imported_modules(_SUBSTRATE_DIR / "_stdlib_ast_helpers.py")
    offenders = mods - _ALLOWED_STDLIB
    assert not offenders, (
        f"_stdlib_ast_helpers.py must stay stdlib-only (it's the whitelisted shared import both "
        f"isolated detectors rely on) -- found: {offenders}")
