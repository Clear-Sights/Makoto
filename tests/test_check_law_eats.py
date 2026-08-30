"""SIGNATURE law: every check declares exactly the context inputs its reachable code reads."""
from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import textwrap
from pathlib import Path

import pytest

from makoto.registry import ALLOWED_EDGES, Check, load_checks
from makoto.context import GateContext
from makoto.kit import DISCHARGE_EATS, _discharge_kwargs


STOP_CONTEXT_FIELDS = frozenset(
    {field.name for field in dataclasses.fields(GateContext)} | {"roots", "is_subagent"}
)
PRE_CONTEXT_FIELDS = frozenset({"current_event", "history", "pattern", "conn"})


def _functions(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _walk_reads(
    root: ast.AST,
    funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    fields: frozenset[str],
    seen: set[str],
    context_names: set[str] | None = None,
) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(root):
        if (isinstance(node, ast.Attribute) and node.attr in fields
                and (context_names is None
                     or isinstance(node.value, ast.Name) and node.value.id in context_names)):
            out.add(node.attr)
        # A literal getattr is just an attribute read expressed dynamically.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in fields
            and (context_names is None
                 or isinstance(node.args[0], ast.Name) and node.args[0].id in context_names)
        ):
            out.add(node.args[1].value)
        if context_names is None and isinstance(node, ast.Name) and node.id in fields:
            out.add(node.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name in funcs and name not in seen:
                seen.add(name)
                callee = funcs[name]
                callee_context = set()
                if context_names is not None:
                    positional = [*callee.args.posonlyargs, *callee.args.args]
                    for arg, parameter in zip(node.args, positional):
                        if isinstance(arg, ast.Name) and arg.id in context_names:
                            callee_context.add(parameter.arg)
                out |= _walk_reads(callee, funcs, fields, seen,
                                   None if context_names is None else callee_context)
    return out


def _check_nodes(tree: ast.Module) -> list[ast.Call]:
    nodes: list[ast.Call] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CHECK" for target in statement.targets
        ):
            if isinstance(statement.value, ast.Call):
                nodes.append(statement.value)
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "EXTRA_CHECKS" for target in statement.targets
        ):
            if isinstance(statement.value, (ast.List, ast.Tuple)):
                nodes.extend(item for item in statement.value.elts if isinstance(item, ast.Call))
    return nodes


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _literal(call: ast.Call, name: str) -> str:
    value = _keyword(call, name)
    assert isinstance(value, ast.Constant) and isinstance(value.value, str)
    return value.value


def _imports_discharge_kwargs(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "makoto.kit"
        and any(alias.name == "_discharge_kwargs" and alias.asname in (None, "_discharge_kwargs")
                for alias in node.names)
        for node in tree.body
    )


def _calls_name(root: ast.AST, funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
                target: str, seen: set[str]) -> bool:
    for node in ast.walk(root):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == target:
                return True
            if node.func.id in funcs and node.func.id not in seen:
                seen.add(node.func.id)
                if _calls_name(funcs[node.func.id], funcs, target, seen):
                    return True
    return False


def derived_reads() -> dict[tuple[str, str], frozenset[str]]:
    reads: dict[tuple[str, str], frozenset[str]] = {}
    package = Path(importlib.import_module("makoto.checks").__file__).parent
    for path in sorted(package.glob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        funcs = _functions(tree)
        module = importlib.import_module(f"makoto.checks.{path.stem}")
        for call in _check_nodes(tree):
            edge = _literal(call, "applies_at")
            check_id = _literal(call, "id")
            fields = PRE_CONTEXT_FIELDS if edge == "Pre" else STOP_CONTEXT_FIELDS
            if edge == "Pre" and "predicate" not in funcs:
                # Factory-built predicates are closures. Their callable body is still the check's
                # entry point; inspect it directly, without following its cross-module callees.
                predicate_tree = ast.parse(textwrap.dedent(inspect.getsource(module.predicate)))
                predicate_funcs = _functions(predicate_tree)
                root = next(iter(predicate_funcs.values()))
                root_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
            else:
                root = funcs["predicate"] if edge == "Pre" else _keyword(call, "run")
                root_funcs = funcs
                if edge != "Pre" and isinstance(root, ast.Name) and root.id in funcs:
                    root = funcs[root.id]
                elif edge != "Pre" and isinstance(root, ast.Name):
                    factory_run = getattr(module, root.id, None)
                    if callable(factory_run):
                        run_tree = ast.parse(textwrap.dedent(inspect.getsource(factory_run)))
                        run_funcs = _functions(run_tree)
                        root = next(iter(run_funcs.values()))
                        root_funcs = {}
            assert root is not None, f"{path}: {check_id} has no analyzable entry point"
            context_names = None
            if edge != "Pre" and isinstance(root, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [*root.args.posonlyargs, *root.args.args]
                context_names = {args[0].arg} if args else set()
            derived = _walk_reads(root, root_funcs, fields, set(), context_names)
            if (
                edge != "Pre"
                and _imports_discharge_kwargs(tree)
                and _calls_name(root, funcs, "_discharge_kwargs", set())
            ):
                derived |= DISCHARGE_EATS
            reads[(check_id, edge)] = frozenset(derived)
    return reads


def _catalog() -> dict[tuple[str, str], Check]:
    return {
        (check.id, check.applies_at): check
        for edge in ALLOWED_EDGES
        for check in load_checks(edge=edge)
    }


@pytest.mark.parametrize("key", sorted(derived_reads()))
def test_check_declares_exactly_what_it_eats(key):
    derived = derived_reads()[key]
    declared = _catalog()[key].eats
    assert derived == declared, (
        f"undeclared={sorted(derived - declared)} overdeclared={sorted(declared - derived)}"
    )


def test_signature_law_catches_an_underdeclared_fixture():
    """Run the law's own derivation over a planted gate, not set arithmetic on two literals.

    This assigned `derived = frozenset({"text"})` by hand and asserted
    `derived - fixture.eats == {"text"}` -- arithmetic on two values the test itself wrote, true
    whatever `_walk_reads` does and even if `_walk_reads` did not exist. It is named for catching
    an underdeclared fixture and it never ran the code that catches one.

    What the parametrised cases above do and do not cover, stated rather than assumed. A
    derivation that goes completely blind IS caught by them: `derived` becomes empty while the
    shipped `eats` declarations are not, so they fail (measured -- planting `return set()` in
    `_walk_reads` reddens 37 of the 38 tests in this module). What they cannot catch is
    CO-DRIFT: a derivation that stops seeing one particular pattern, in a repository where the
    `eats` declarations were written by reading that same derivation's output. Then both sides
    move together and equality still holds. This test is the independent anchor for that case --
    a body whose reads are known by construction, not by asking the derivation.

    The plant is a gate body that READS a context field and declares nothing, put through
    `_walk_reads` exactly as `derived_reads()` puts the real ones. Its control is in the same
    test: a body reading nothing must derive nothing, so a derivation that simply returns every
    field cannot pass either.
    """
    underdeclared = ast.parse(
        "def run(ctx):\n"
        "    if ctx.text:\n"
        "        return ctx.touched\n"
        "    return None\n"
    )
    body = next(iter(_functions(underdeclared).values()))
    derived = _walk_reads(body, _functions(underdeclared), STOP_CONTEXT_FIELDS, set(), {"ctx"})
    fixture = Check("fixture.underdeclared", "Stop", "ADVISE", eats=frozenset())
    assert derived == {"text", "touched"}, (
        f"the derivation no longer sees fields a gate body reads: got {sorted(derived)}, "
        f"expected text and touched from a body that reads exactly those two."
    )
    assert derived - fixture.eats == {"text", "touched"}, (
        "the law does not report a gate that reads context fields it declares none of"
    )

    silent = ast.parse("def run(ctx):\n    return None\n")
    quiet = next(iter(_functions(silent).values()))
    assert _walk_reads(quiet, _functions(silent), STOP_CONTEXT_FIELDS, set(), {"ctx"}) == set(), (
        "CONTROL: a body that reads no context field must derive nothing; a derivation that "
        "returns every field would satisfy the assertions above without seeing anything"
    )


def test_discharge_eats_matches_helper_body_exactly():
    tree = ast.parse(inspect.getsource(_discharge_kwargs))
    helper = next(iter(_functions(tree).values()))
    derived = _walk_reads(helper, _functions(tree), STOP_CONTEXT_FIELDS, set(), {"c"})
    assert derived == DISCHARGE_EATS
