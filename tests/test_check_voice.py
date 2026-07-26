"""SPEC-C item 5 (one voice): a check's retry_hint/description must be a MODULE-LEVEL string
CONSTANT in its own file, not an inline literal buried inside the `Check(...)` call -- this is
what makes the hint/detector-mismatch class this session found and fixed TWICE (gate.named_test's
quoted-retraction FP, canon.timeout's retry_hint over-promise) structurally hard to recreate: a
grep for the file's own top-level assignments shows every voice string at a glance, instead of
requiring a reader to parse out a long inline kwarg to find it.

Stop-tier gates that build MULTIPLE distinct finding kinds (hollowTest.py's _KIND_MESSAGE dict,
canonTimeoutRecur.py's CANON_SEQ_PRIMITIVES tuples) already satisfy the SAME anti-duplication
property by a different, arguably stronger shape (one dict/tuple co-locating every sub-kind's
text, rather than a single bare string) -- this test only requires the literal RETRY_HINT/
DESCRIPTION constant shape for checks that actually declare a single retry_hint/description on
their CHECK export (today: every Pre-tier check), since that is the exact shape this session's
migration produced and the exact shape the spec's own step 1 describes.
"""
from __future__ import annotations
import ast
import inspect

from makoto.substrate._loader import discover


def _module_level_names(mod) -> set:
    """Every name assigned at MODULE level (not inside a function/class) in `mod`'s own source."""
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    names = set()
    for node in tree.body:   # tree.body only -- module level, not nested scopes
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def test_every_check_with_a_retry_hint_declares_it_as_a_module_level_constant():
    violations = []
    for c in discover():
        if not c.retry_hint:
            continue
        mod = __import__(c.predicate_module, fromlist=["_"]) if c.predicate_module else None
        if mod is None:
            continue
        if "RETRY_HINT" not in _module_level_names(mod):
            violations.append(c.id)
    assert not violations, (
        f"these checks' retry_hint is not a module-level RETRY_HINT constant: {violations}"
    )


def test_every_check_with_a_description_declares_it_as_a_module_level_constant():
    violations = []
    for c in discover():
        if not c.description:
            continue
        mod = __import__(c.predicate_module, fromlist=["_"]) if c.predicate_module else None
        if mod is None:
            continue
        if "DESCRIPTION" not in _module_level_names(mod):
            violations.append(c.id)
    assert not violations, (
        f"these checks' description is not a module-level DESCRIPTION constant: {violations}"
    )


def test_the_check_export_references_the_constant_not_a_second_literal():
    """Teeth: the CHECK export's own source line must use the NAME (RETRY_HINT/DESCRIPTION), not
    a second, independently-typed string literal -- the exact duplication this item exists to
    prevent (a name and a literal can never silently drift apart; two literals can)."""
    for c in discover():
        if not (c.retry_hint and c.description) or not c.predicate_module:
            continue
        mod = __import__(c.predicate_module, fromlist=["_"])
        src = inspect.getsource(mod)
        check_line = next(l for l in src.splitlines() if l.strip().startswith("CHECK = "))
        assert "retry_hint=RETRY_HINT" in check_line, f"{c.id}: CHECK export doesn't reference RETRY_HINT by name"
        assert "description=DESCRIPTION" in check_line, f"{c.id}: CHECK export doesn't reference DESCRIPTION by name"
