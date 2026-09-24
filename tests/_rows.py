"""The rows of the four shape modules, read from source.

A shape module (`makoto/checks/<shape>.py`) holds its checks as rows: `<key>_CHECK = _Check(...)`.
A Stop row's verdict starts at its `run`; a Pre row's at the function `_PREDICATES` names for its
id. Each law over rows reads them here, so a row cannot slip past one law by being shaped
differently from what another expects.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import textwrap
from dataclasses import dataclass
from pathlib import Path

SHAPES = {"spec": "SPEC", "otherPoint": "OTHER_POINT", "switch": "SWITCH", "lineage": "LINEAGE"}


def functions(tree: ast.AST) -> dict:
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


@dataclass(frozen=True)
class Row:
    key: str                 # the `<key>` of `<key>_CHECK`
    id: str
    edge: str
    module: object
    tree: ast.Module
    funcs: dict
    binds: dict              # top-level `name = <expr>` assignments of the module
    call: ast.Call           # the `_Check(...)` call
    entry: str | None        # the name the verdict starts at, when it is a name
    root: ast.AST            # where the verdict starts
    root_funcs: dict         # the functions a walk from `root` may follow by name


def _keyword(call: ast.Call, name: str):
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _resolve(name: str, module, funcs: dict):
    """A name the row's verdict starts at: its def in the shape module, or -- a closure a factory
    built -- the closure's own body, or -- imported, now or when the row runs -- its def followed
    within its own module."""
    if name in funcs:
        body = funcs[name].body
        if len(body) == 2 and isinstance(body[0], ast.ImportFrom):
            # `from M import f; return f(ctx)`: a row that defers its import delegates to `f`.
            fn = getattr(importlib.import_module(body[0].module), body[0].names[0].name)
            home = functions(ast.parse(Path(inspect.getsourcefile(fn)).read_text()))
            return home[fn.__name__], home
        return funcs[name], funcs
    fn = getattr(module, name)
    if "<locals>" in fn.__qualname__:
        return next(iter(functions(ast.parse(textwrap.dedent(inspect.getsource(fn)))).values())), {}
    home = functions(ast.parse(Path(inspect.getsourcefile(fn)).read_text()))
    return home[fn.__name__], home


def rows() -> dict:
    package = Path(importlib.import_module("makoto.checks").__file__).parent
    out = {}
    for stem in SHAPES:
        path = package / f"{stem}.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        module = importlib.import_module(f"makoto.checks.{stem}")
        funcs = functions(tree)
        binds = {t.id: s.value for s in tree.body if isinstance(s, (ast.Assign, ast.AnnAssign))
                 for t in getattr(s, "targets", [getattr(s, "target", None)])
                 if isinstance(t, ast.Name) and s.value is not None}
        predicates = {}
        pmap = binds.get("_PREDICATES")
        if isinstance(pmap, ast.Dict):
            for k, v in zip(pmap.keys, pmap.values):
                predicates[k.value.id[:-len("_CHECK")]] = v.id
        for name, value in binds.items():
            if not (name.endswith("_CHECK") and isinstance(value, ast.Call)):
                continue
            key = name[:-len("_CHECK")]
            edge = _keyword(value, "applies_at").value
            run = _keyword(value, "run")
            if edge == "Pre":
                entry = predicates[key]
                root, root_funcs = _resolve(entry, module, funcs)
            elif isinstance(run, ast.Name):
                entry = run.id
                root, root_funcs = _resolve(entry, module, funcs)
            else:
                entry, root, root_funcs = None, run, funcs
            out[(_keyword(value, "id").value, edge)] = Row(
                key, _keyword(value, "id").value, edge, module, tree, funcs, binds, value,
                entry, root, root_funcs)
    return out


def reached(row: Row) -> set:
    """Every name the row's verdict reaches, following the defs and binds of its own module."""
    defs, seen, out = {**row.binds, **row.funcs}, set(), set()
    stack = [row.binds.get(row.entry, row.root)]
    while stack:
        for node in ast.walk(stack.pop()):
            name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
            if name:
                out.add(name)
            if name in defs and name not in seen:
                seen.add(name)
                stack.append(defs[name])
    return out
