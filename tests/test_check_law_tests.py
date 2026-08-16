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
    "claim_vs_ledger_predicate": "CLAIM_VS_LEDGER",
    "live_query_finding": "LIVE_QUERY",
    # "introduced_regex_predicate" is NOT listed here: it serves both PATTERN_MATCH and
    # CLAIM_VS_HISTORY callers (illusoryAuthorshipTrailer.py / illusoryInterruptionClaim.py),
    # so its shape isn't derivable from factory NAME alone — see _factory_shape's special case
    # below, which derives it from whether the call site passes `grounded_in_history=` instead.
    # That's still a literal AST check on the call's own keywords, not a runtime value or a
    # trusted manifest, so the law keeps verifying the declared shape from source.
}

ONE_OFF = {
    "content.self_mute_guard": "hardcoded makoto-allow immunity cannot use universal routing",
    "gate.contract_order": "one module owns both its Pre and Stop surfaces",
    "gate.undeclared_falsifiable": "meta-level audit over registry/loader completeness",
    "gate.green_claim": "genuine CLAIM_VS_HISTORY / TESTRUN_DELTA straddle",
}

HISTORY_PRIMITIVES = frozenset({
    "iter_tool_events", "raw_payload_str", "decode_history_row", "turn_tool_calls",
    "calls_from_history",
})
LEDGER_PRIMITIVES = frozenset({"_discharged", "_discharge_kwargs", "_drop_discharged"})
TESTRUN_PRIMITIVES = frozenset({
    "classify_failure", "compute_delta", "recorded_failed_names", "is_failing_testrun",
    "_bash_call_after",
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


def _has_required_evidence(shape: str, tree: ast.Module) -> bool:
    calls = _module_calls(tree)
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
            f"{key}: declares {check.tests} without its required evidence primitive"
        )


def test_result_shape_law_catches_an_underdeclared_fixture():
    fixture = Check("fixture.underdeclared", "Stop", "ADVISE", tests="CLAIM_VS_LEDGER")
    tree = ast.parse("def run(c):\n    return None\n")
    assert fixture.tests in TESTS_SHAPES
    assert not _has_required_evidence(fixture.tests, tree)
