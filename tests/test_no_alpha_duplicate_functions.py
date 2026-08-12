"""Standing regression gate: no two functions ANYWHERE in the package do the same thing under
different names. Two functions are "alpha-equivalent" here if their AST is structurally identical
after stripping docstrings and alpha-renaming local variables/args to positional placeholders --
the same notion of equivalence compilers use, not a token-similarity heuristic.

Scan set widened 2026-07-09 from checks/+substrate/ to every domain package plus root modules:
the original narrow set was a real coverage gap in the gate itself -- record/audit.py carried a
self-clone, and contractOrder/plan + selfWiredCheck/install carried whole-function duplicates,
none of which the old scan could ever have seen. A gate that scans a subset silently certifies
the rest; the scan set is now the package, minus tests/ (test files legitimately repeat shapes).

Exemption list is EXPLICIT and justified, never a blanket suppression: an entry here means the
duplication was checked and found necessary, not merely convenient. Each exemption records its
reason inline below.
"""
from __future__ import annotations

import ast
import hashlib
from copy import copy
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent / "makoto"

# (file, function) pairs allowed to be alpha-equivalent, with the reason on record.
_EXEMPT_PAIRS = {
    frozenset({("substrate/_stdlib_ast_helpers.py", "_callee_chain"), ("substrate/factories.py", "callee_chain")}):
        "deliberate: _stdlib_ast_helpers.py must stay stdlib-only so deadPureStatement.py/"
        "hollowTest.py keep their import-graph isolation (enforced by "
        "test_detector_engines_are_stdlib_isolated.py) -- importing substrate.factories here would break "
        "the property the duplication exists to protect.",
    frozenset({("checks/contractOrder.py", "_load_plan"), ("session/plan.py", "load_plan")}):
        "deliberate: contractOrder is a discovered Stop gate, and the gate-side layering firewall "
        "(tests/test_gate_shape.py, ALLOWED_IMPORT_ROOTS -- an ENFORCED check, verified 2026-07-09, "
        "not a docstring claim) bars it from importing makoto.session.plan, the L2 store. Its PRE "
        "predicate therefore reads the plans table inline via its own conn -- 12 lines of SQL "
        "duplicated on purpose, per the repo's own boundary law ('shapes are copied, never "
        "imported'). Merging would require widening the firewall, an owner-level design change.",
}


def _canonicalize(node: ast.AST, names: dict) -> ast.AST:
    if isinstance(node, ast.Name):
        names.setdefault(node.id, f"_v{len(names)}")
        return ast.Name(id=names[node.id], ctx=type(node.ctx)())
    if isinstance(node, ast.arg):
        names.setdefault(node.arg, f"_v{len(names)}")
        return ast.arg(arg=names[node.arg], annotation=None)
    # Preserve constructor-only fields introduced by newer Python AST node classes.  Constructing
    # a blank node and filling only iter_fields worked through 3.12 but emits one deprecation
    # warning per node on 3.13 (and becomes an error in 3.15).
    new = copy(node)
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            setattr(new, field, [_canonicalize(v, names) if isinstance(v, ast.AST) else v for v in value])
        elif isinstance(value, ast.AST):
            setattr(new, field, _canonicalize(value, names))
        else:
            setattr(new, field, value)
    for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset"):
        if hasattr(node, attr):
            setattr(new, attr, 0)
    return new


def _signature(fn_node: ast.FunctionDef) -> tuple:
    names: dict = {}
    body = [n for n in fn_node.body
            if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str))]
    canon = [ast.dump(_canonicalize(n, names)) for n in body]
    return hashlib.sha256("\n".join(canon).encode()).hexdigest(), len(body)


def _scan() -> dict:
    groups = defaultdict(list)
    scan = [py for d in ("checks", "substrate", "record", "verdict", "session", "core",
                         "stopchecks", "tools")
            for py in sorted((_ROOT / d).glob("*.py")) if (_ROOT / d).is_dir()]
    scan += sorted(_ROOT.glob("*.py"))  # root entry-point modules (_dispatch.py, install.py, ...)
    for py in scan:
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                h, nstmts = _signature(node)
                if nstmts >= 2:  # skip trivial one-liners, too noisy to be meaningful
                    rel = str(py.relative_to(_ROOT))
                    groups[h].append((rel, node.name))
    return groups


def test_no_unexempted_alpha_duplicate_functions():
    groups = _scan()
    offenders = []
    for members in groups.values():
        if len(members) < 2:
            continue
        pair = frozenset(members)
        if pair in _EXEMPT_PAIRS:
            continue
        offenders.append(members)
    assert offenders == [], (
        f"alpha-equivalent function(s) found outside the exemption list: {offenders}")


def test_every_exempt_pair_is_still_alpha_equivalent():
    """An exemption that stops being true (someone edits one side) should fail loudly, not linger
    as stale documentation."""
    groups = _scan()
    live_pairs = {frozenset(members) for members in groups.values() if len(members) >= 2}
    for pair in _EXEMPT_PAIRS:
        assert pair in live_pairs, f"exempted pair no longer alpha-equivalent, remove the exemption: {pair}"
