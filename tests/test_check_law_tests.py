"""RESULT-SHAPE law: every check declares and evidences exactly one verdict shape."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from makoto.registry import ALLOWED_EDGES, TESTS_SHAPES, Check, load_checks


FACTORY_SHAPES = {
    "ast_introduced_predicate": "PATTERN_MATCH",
    "regex_file_predicate": "PATTERN_MATCH",
    "claim_vs_history_predicate": "CLAIM_VS_HISTORY",
    "live_query_finding": "LIVE_QUERY",
    "unmet_obligation_gate": "ACT_VS_GUARD",
    # "introduced_regex_predicate" is NOT listed here: it serves both PATTERN_MATCH and
    # CLAIM_VS_HISTORY callers (illusoryAuthorshipTrailer.py / illusoryInterruptionClaim.py),
    # so its shape isn't derivable from factory NAME alone — see _factory_shape's special case
    # below, which derives it from whether the call site passes `grounded_in_history=` instead.
    # That's still a literal AST check on the call's own keywords, not a runtime value or a
    # trusted manifest, so the law keeps verifying the declared shape from source.
}

ONE_OFF = {
    "content.self_mute_guard": "hardcoded makoto-allow immunity cannot use universal routing",
    "gate.undeclared_falsifiable": "meta-level audit over registry/loader completeness",
    "gate.green_claim": "genuine CLAIM_VS_HISTORY / TESTRUN_DELTA straddle",
}

HISTORY_PRIMITIVES = frozenset({
    "iter_tool_events", "raw_payload_str", "decode_history_row", "decode_history_event",
    "turn_tool_calls", "calls_from_history",
    # `calls_since` is `calls_from_history` with the atom window applied (the calls since the
    # operator last spoke). It reads the same history rows through the same decoder, so it is the
    # same primitive at a narrower quantifier -- not a second way of consulting history.
    "calls_since",
    # `user_turn_texts` is the ORACLE half of the same session record: the host-written user
    # turns, read as the record a claim ABOUT the operator is held against. Same session, same
    # spoof-resistance (`_is_genuine_user_turn`), different channel.
    "user_turn_texts",
})
LEDGER_PRIMITIVES = frozenset({"_discharged", "_discharge_kwargs", "_drop_discharged"})
# An obligation's evidence is the ORDERED event sequence, so its primitive is the factory that
# walks it. The factory is the only way to reach that walk: a module that declares ACT_VS_GUARD
# and hand-rolls the loop instead fails this law, which is the point -- one home for the order
# rule, since the order IS the check.
ACT_GUARD_PRIMITIVES = frozenset({"unmet_obligation_gate"})
TESTRUN_PRIMITIVES = frozenset({
    "classify_failure", "compute_delta", "recorded_failed_names", "is_failing_testrun",
    "_bash_call_after",
    # `current_named_verdicts` is the same family at the grain a per-test verdict needs: it
    # builds {exact_id: FAIL|PASS} out of the responses of RECOGNIZED runner invocations only,
    # over the same `recorded_failed_names`/`recorded_passed_names` parsers the others use. A
    # gate reaching it has consulted a test run, which is what this shape's evidence means --
    # and reaching it is the only sound way to do so, because it is what keeps a `FAILED` line
    # the agent merely displayed (`cat old.log`) from grounding a verdict.
    "current_named_verdicts",
})
INTRODUCED_PRIMITIVES = frozenset({
    "_gated_content", "scan_target_content", "introduced_text",
    "iter_touched_python_sources", "calls_from_history", "fired_canon_fingerprints",
})
LIVE_PRIMITIVES = frozenset({
    "open", "stale_failing_node", "read_plugin_manifest_hooks",
    "_read_plugin_manifest_hooks",
})


def _functions(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts = [node.func.attr]
        value = node.func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _walk_calls(root: ast.AST, funcs, seen: set[str]) -> set[str]:
    """Same-module reachable call graph, mirroring the eats law's `_walk_reads`."""
    out: set[str] = set()
    for node in ast.walk(root):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name:
            out.add(name)
        short = name.rsplit(".", 1)[-1]
        if short in funcs and short not in seen:
            seen.add(short)
            out |= _walk_calls(funcs[short], funcs, seen)
    return out


def _introduced_regex_predicate_shape(node: ast.Call) -> str:
    """`introduced_regex_predicate` alone serves both PATTERN_MATCH and CLAIM_VS_HISTORY callers
    (see kit.py's own docstring) — its shape is derived from whether the call passes
    `grounded_in_history=`, a literal keyword on THIS call node, not a runtime value or a name
    lookup. Still a source-derived verdict, not a trusted declaration."""
    return "CLAIM_VS_HISTORY" if any(kw.arg == "grounded_in_history" for kw in node.keywords) \
        else "PATTERN_MATCH"


def _factory_shape(tree: ast.Module) -> str | None:
    shapes = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node).rsplit(".", 1)[-1]
        if name == "introduced_regex_predicate":
            shapes.add(_introduced_regex_predicate_shape(node))
        elif name in FACTORY_SHAPES:
            shapes.add(FACTORY_SHAPES[name])
    assert len(shapes) <= 1, f"module mixes result-shape factories: {sorted(shapes)}"
    return next(iter(shapes), None)


def _module_calls(tree: ast.Module) -> set[str]:
    funcs = _functions(tree)
    calls = _walk_calls(tree, funcs, set())
    return calls | {name.rsplit(".", 1)[-1] for name in calls}


def _discarded_calls(tree: ast.Module) -> set[str]:
    """Primitives called as a BARE STATEMENT, so whatever they return is thrown away.

    `_module_calls` answers "is this primitive called". A call whose result nothing reads is not
    evidence: the check can call the history reader, ignore what it says, and return a verdict
    reached some other way, while the shape law sees the name and passes. Only calls in
    statement position are collected here -- a call inside a comparison, an assignment, a return
    or an argument is used by definition.
    """
    discarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            name = _call_name(node.value)
            if name:
                discarded.add(name)
                discarded.add(name.rsplit(".", 1)[-1])
    return discarded


def _has_required_evidence(shape: str, tree: ast.Module) -> bool:
    # A primitive whose result is discarded does not count as having been consulted.
    calls = _module_calls(tree) - _discarded_calls(tree)
    if shape == "CLAIM_VS_HISTORY":
        return bool(calls & HISTORY_PRIMITIVES)
    if shape == "CLAIM_VS_LEDGER":
        if calls & LEDGER_PRIMITIVES:
            return True
        return any(
            isinstance(node, ast.Call) and _call_name(node) == "getattr"
            and len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "open_plan_items"
            for node in ast.walk(tree)
        )
    if shape == "ACT_VS_GUARD":
        return bool(calls & ACT_GUARD_PRIMITIVES)
    if shape == "TESTRUN_DELTA":
        return bool(calls & TESTRUN_PRIMITIVES)
    if shape == "LIVE_QUERY":
        return bool(calls & LIVE_PRIMITIVES) or any(
            name in {"os.path.exists", "os.path.getsize"} or name.startswith("subprocess.")
            for name in calls
        )
    if shape == "PATTERN_MATCH":
        match_call = any(
            name in {"re.search", "re.match", "ast.walk"}
            or name.endswith((".search", ".match", ".finditer"))
            for name in calls
        )
        gated = bool(calls & INTRODUCED_PRIMITIVES) or any(
            isinstance(node, ast.Constant) and node.value in {"current_event", "touched", "text"}
            for node in ast.walk(tree)
        )
        return match_call and gated
    return False


def test_no_dead_result_shape_in_the_closed_vocabulary():
    """`TESTS_SHAPES` is a CLOSED vocabulary, and nothing checked the other direction: a shape
    nobody declares sits in it undetectably. That is `B7 RULE WITH NO RUNNER` applied to a
    vocabulary rather than to a rule, and a plant on 2026-09-18 -- adding a bogus shape --
    left the whole suite green.

    Every member must be declared by at least one live check, or be named in `RESERVED_SHAPES`
    with the reason. `FACTORY_SHAPES`' values must also all be real members, so a factory cannot
    be mapped to a shape the vocabulary does not carry.
    """
    RESERVED_SHAPES: dict[str, str] = {}      # none reserved today; a member here needs a reason
    declared = {c.tests for c in _catalog().values() if c.tests}
    dead = sorted(TESTS_SHAPES - declared - set(RESERVED_SHAPES))
    assert not dead, (
        f"result shape(s) in TESTS_SHAPES that no live check declares: {dead}. Either a check "
        f"should declare one, or the member is dead vocabulary and comes out.")
    invented = sorted(set(FACTORY_SHAPES.values()) - TESTS_SHAPES)
    assert not invented, f"FACTORY_SHAPES maps a factory to shape(s) the vocabulary lacks: {invented}"
    assert not (declared - TESTS_SHAPES), "a live check declares a shape outside the vocabulary"


def _catalog() -> dict[tuple[str, str], Check]:
    return {
        (check.id, check.applies_at): check
        for edge in ALLOWED_EDGES
        for check in load_checks(edge=edge)
    }


def _source_trees(package: Path) -> dict[tuple[str, str], ast.Module]:
    out = {}
    for path in sorted(package.glob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keywords = {kw.arg: kw.value for kw in node.keywords}
            id_node = keywords.get("id")
            edge_node = keywords.get("applies_at")
            if (
                isinstance(id_node, ast.Constant) and isinstance(id_node.value, str)
                and isinstance(edge_node, ast.Constant) and isinstance(edge_node.value, str)
            ):
                out[(id_node.value, edge_node.value)] = tree
    return out


def _cases():
    package = Path(importlib.import_module("makoto.checks").__file__).parent
    catalog = _catalog()
    trees = _source_trees(package)
    for key, check in sorted(catalog.items()):
        yield key, check, trees[key]


@pytest.mark.parametrize("key,check,tree", list(_cases()), ids=lambda value: str(value))
def test_check_declares_and_evidences_result_shape(key, check, tree):
    if check.id in ONE_OFF:
        assert check.tests == "", f"registered ONE_OFF must remain undeclared: {ONE_OFF[check.id]}"
        return
    assert check.tests in TESTS_SHAPES, f"{key}: undeclared tests shape"
    factory_shape = _factory_shape(tree)
    if factory_shape is not None:
        assert check.tests == factory_shape
    else:
        assert _has_required_evidence(check.tests, tree), (
            f"{key}: declares {check.tests} without its required evidence primitive, or calls "
            f"one only as a bare statement and discards what it returns. STATED LIMIT: this "
            f"law reads the module's source -- it establishes that the primitive is consulted "
            f"and its result used, not that the verdict is derived from it. The behavioural "
            f"half is tests/predicates/<check>.py and the universal law in "
            f"tests/test_stop_gate_level_invariant.py."
        )


def test_result_shape_law_catches_an_underdeclared_fixture():
    fixture = Check("fixture.underdeclared", "Stop", "ADVISE", tests="CLAIM_VS_LEDGER")
    tree = ast.parse("def run(c):\n    return None\n")
    assert fixture.tests in TESTS_SHAPES
    assert not _has_required_evidence(fixture.tests, tree)
