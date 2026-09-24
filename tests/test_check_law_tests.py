"""FAMILY law: every row sits in its family's module, and decides the way its family decides.

The register has four families, and each names what pays a check's subject. SPEC holds its own
definition and needs no witness. The other three owe a witness -- a second reading of the subject
(OTHER_POINT), an act and its response (SWITCH), a read of the source before the write drawn from
it (LINEAGE) -- and every one of them decides through the one engine, `kit.unwitnessed`. So the
law is one line per direction: a witness family's row reaches the engine, a SPEC row does not.

STATED LIMIT: this reads source. It establishes that the engine is on the row's reachable path,
not that the verdict comes from it; the behavioural half is the engine's own plant (a witness
that never pays turns the suite red) and each row's tests.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from makoto import kit
from makoto.registry import ALLOWED_EDGES, TESTS_SHAPES, load_checks
from tests._rows import SHAPES, functions, rows

# `introduced_regex_predicate` pays through the engine only when handed a witness.
_OPTIONAL_WITNESS = {"introduced_regex_predicate": "grounded_in_history"}


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _reaches(root: ast.AST, defs: dict, target: set, seen: set) -> bool:
    """Whether `root` calls, or names, anything in `target`, following the names `defs` binds."""
    for node in ast.walk(root):
        name = _call_name(node) if isinstance(node, ast.Call) else \
            node.id if isinstance(node, ast.Name) else ""
        if name in target:
            witness = _OPTIONAL_WITNESS.get(name)
            if witness is None or isinstance(node, ast.Call) and any(kw.arg == witness for kw in node.keywords):
                return True
        if name in defs and name not in seen:
            seen.add(name)
            if _reaches(defs[name], defs, target, seen):
                return True
    return False


def _engine() -> set:
    """`unwitnessed` and every kit function whose own body reaches it."""
    kit_defs = functions(ast.parse(inspect.getsource(kit)))
    return {"unwitnessed"} | {n for n in kit_defs if _reaches(kit_defs[n], kit_defs, {"unwitnessed"}, set())}


def _decides_through_engine(row) -> bool:
    start = row.binds[row.entry] if row.entry in row.binds else row.root
    return _reaches(start, {**row.binds, **row.funcs}, _engine(), set())


_ROWS = rows()


def test_every_live_check_is_a_row_of_a_shape_module():
    live = {(c.id, c.applies_at) for edge in ALLOWED_EDGES for c in load_checks(edge=edge)}
    assert live == set(_ROWS), f"only-live={sorted(live - set(_ROWS))} only-rows={sorted(set(_ROWS) - live)}"


def test_the_vocabulary_is_the_four_families_and_each_holds_a_row():
    assert TESTS_SHAPES == set(SHAPES.values())
    assert {row.module.__name__.rsplit(".", 1)[-1] for row in _ROWS.values()} == set(SHAPES)


@pytest.mark.parametrize("key", sorted(_ROWS), ids=str)
def test_row_declares_its_module_family_and_decides_as_that_family(key):
    row = _ROWS[key]
    family = SHAPES[row.module.__name__.rsplit(".", 1)[-1]]
    declared = row.module.ROWS[row.id].tests
    assert declared == family, f"{key}: declares {declared!r} but sits in the {family} module"
    if family == "SPEC":
        assert not _decides_through_engine(row), f"{key}: a SPEC row holds its definition; it owes no witness"
    else:
        assert _decides_through_engine(row), f"{key}: a {family} row owes a witness and must decide through kit.unwitnessed"


def test_family_law_catches_planted_rows():
    engine = _engine()
    witnessed = ast.parse("def run(ctx):\n    return next(unwitnessed(ctx.events, owes=f, pays=g), None)\n")
    bare = ast.parse("def run(ctx):\n    return None\n")
    unwitnessed_factory = ast.parse("p = introduced_regex_predicate(body_rx=R)\n")
    witnessed_factory = ast.parse("p = introduced_regex_predicate(body_rx=R, grounded_in_history=g)\n")
    assert _reaches(witnessed, functions(witnessed), engine, set())
    assert not _reaches(bare, functions(bare), engine, set())
    assert not _reaches(unwitnessed_factory, {}, engine, set())
    assert _reaches(witnessed_factory, {}, engine, set())


def test_every_advisory_gate_declares_the_fields_its_tier_rests_on():
    """The allowlist and the declared posture must name the same set: the README's
    blocking/advisory counts are published off the allowlist and its posture off the check.
    `may_block=True` is what puts a check in the decision pipeline, so only those are compared."""
    from makoto.registry import _ADVISORY_ALLOWLIST, POSTURE_ADVISE, POSTURE_BLOCK
    stop = {row.id: row.module.ROWS[row.id] for row in _ROWS.values() if row.edge == "Stop"}
    pipeline = {cid: c for cid, c in stop.items() if getattr(c, "may_block", False)}
    advisory_by_posture = {cid for cid, c in pipeline.items() if c.posture == POSTURE_ADVISE}
    assert advisory_by_posture == set(_ADVISORY_ALLOWLIST), (
        f"only-posture={sorted(advisory_by_posture - set(_ADVISORY_ALLOWLIST))} "
        f"only-allowlist={sorted(set(_ADVISORY_ALLOWLIST) - advisory_by_posture)}")
    for cid, c in stop.items():
        assert c.posture in (POSTURE_ADVISE, POSTURE_BLOCK), cid
