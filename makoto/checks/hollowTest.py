"""gate.hollow_test's pure AST analyzer: a HOLLOWED-class detector (SPIRIT.md §4) — a test that
survives in name while its content is gutted. Four independently-firing sub-patterns, each
zero-FP by construction or by corpus measurement (see tests/test_hollow_test_fp.py):

  1. no_assertion       — the test body asserts nothing at all (no `assert`, no assertion-shaped
                           call), and is not an explicitly `@skip`-decorated stub.
  2. tautology           — an `assert True`, or an `assert x == x` / `assert x is x` where both
                           sides of the comparison are the textually-identical expression AND
                           neither side contains a Call (a call can return a different object/value
                           on each evaluation — e.g. `assert cache() is cache()` is a genuine
                           memoization/identity check, not a tautology, even though both sides are
                           syntactically identical; corpus-found FP, see test_gate_shape.py's own
                           `assert load_stopchecks() is load_stopchecks()`).
  3. swallowed_failure   — a `try` around the call-under-test whose only `except` is both BROAD
                           (bare/`Exception`/`BaseException`) and a no-op, with no assertion
                           anywhere else in the function to catch a failure.
  4a. uncollectable_nested      — a test-shaped `def test_*` nested inside another function's body.
                           pytest's own collector never descends into a function looking for further
                           `def`s, so this can never be independently run/skipped/reported — only
                           flagged when its OWN body contains a recognized assertion (an incidentally
                           `test_`-named private helper with no real check inside is not a finding).
  4b. uncollectable_always_skip — a `skipif`/`skipIf` guard (decorator, or a function-body
                           `if <cond>: pytest.skip(...)` / `raise unittest.SkipTest(...)` guard as the
                           function's first statement, or a module-level `pytestmark =
                           pytest.mark.skipif(...)`) whose condition is PROVABLY always-true by the
                           same `_is_tautology` predicate already proven zero-FP for sub-pattern 2. A
                           bare, argument-less `@pytest.mark.skip(...)` / `@unittest.skip(...)` (no
                           condition at all) is explicitly NOT this pattern — that is an honest,
                           transparently-labeled skip (SPIRIT.md §4 INCOMPLETE), not a disguised one.

SPEC-5 Task 4 (owner-revised layout): the analyzer engine (formerly `stopchecks/hollow_test.py`)
and its Stop-hook adapter (formerly `stopchecks/stopcheck_hollow_test.py`) are combined into ONE
flat file here — the migration ticket left single-vs-paired-file layout to the executing session's
call; a single file is chosen because the two halves are always read/changed together and a flat
`checks/` package favors one file per detector, matching every other migrated check. The analyzer
itself is self-contained (zero imports beyond stdlib `ast`); the `makoto-allow` exemption and the
GateContext plumbing live in the adapter half below — this discipline is unchanged from the split
layout, only the file boundary moved.
"""
from __future__ import annotations
import ast

from makoto.substrate._stdlib_ast_helpers import _callee_chain, iter_touched_python_sources
from makoto.core.schema import Finding

_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_BROAD_EXC_NAMES = ("Exception", "BaseException")


# ---- filename / test-function scope gate -------------------------------------------------------
def _is_test_filename(path: str) -> bool:
    """pytest's own default `python_files` discovery convention: `test_*.py` or `*_test.py`."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def _bases_are_unittest_style(class_node) -> bool:
    return any("TestCase" in ast.dump(b) for b in class_node.bases)


def _iter_test_functions(tree):
    """Yields every module-level function/async-function whose name starts with `test_` (pytest's
    `python_functions` convention), plus every method of a module-level class whose name starts
    with `Test` AND whose base list textually includes something containing `TestCase` (unittest
    style) — for such a class, a bare `test`-prefixed method name (no underscore) also counts."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            yield node
        elif isinstance(node, ast.ClassDef):
            is_unittest = node.name.startswith("Test") and _bases_are_unittest_style(node)
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if child.name.startswith("test_"):
                    yield child
                elif is_unittest and child.name.startswith("test"):
                    yield child


# ---- own-scope traversal (recurse into control-flow blocks, never into a nested def/lambda/class)
def _walk_own_scope(node):
    yield node
    if isinstance(node, _NESTED_SCOPES):
        return                                              # a nested scope: do not descend further
    for child in ast.iter_child_nodes(node):
        yield from _walk_own_scope(child)


def _iter_own_scope(stmts):
    for s in stmts:
        yield from _walk_own_scope(s)


# ---- the assertion recognizer (generous by design: an FN here only suppresses a fire) -----------
# _callee_chain imported at module top from _stdlib_ast_helpers (2026-07-09: was a local duplicate
# of both deadPureStatement.py's usage pattern and lib/factories.py::callee_chain; extracted rather
# than left duplicated -- see tests/test_detector_engines_are_stdlib_isolated.py).
def _is_assertion_call(node) -> bool:
    """Generous recognizer: any Call whose dotted callee has a component (case-insensitive)
    starting with `assert` (`self.assertTrue`, `assert_that(...)`, `mock.assert_called_with`), OR
    whose last component is exactly `fail` (`self.fail(...)`, `pytest.fail(...)`), OR whose chain
    is exactly `pytest.raises`. Being generous here is FN-safe: it can only make a sub-pattern fire
    LESS, never more."""
    if not isinstance(node, ast.Call):
        return False
    chain = _callee_chain(node)
    if not chain:
        return False
    parts = chain.split(".")
    if any(p.lower().startswith("assert") for p in parts):
        return True
    if parts[-1] == "fail":
        return True
    return chain == "pytest.raises"


def _local_helper_index(tree):
    """name -> FunctionDef/AsyncFunctionDef node, for every MODULE-LEVEL function (methods and
    nested defs excluded). A same-file, name-resolved fact only — never a general call-graph
    solver, and never crossing file boundaries."""
    idx = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            idx[node.name] = node
    return idx


def _helper_names_that_assert(tree) -> frozenset:
    """Names of module-level helper functions whose own body (transitively, through calls to other
    same-file module-level helpers) contains a recognized assertion. Extends the recognizer to the
    extremely common 'shared assert helper' pattern (a test's only observable check is a call to a
    same-file helper like `_clean(call)` / `_assert_ok(x)` that itself does `assert not x.fired`) --
    corpus-found FP class (assay's test_forbidden_location.py). Generous/FN-safe by construction:
    it can only make a sub-pattern fire LESS, never more. Bounded fixpoint over a finite function
    set, so it always terminates."""
    idx = _local_helper_index(tree)
    asserts: set = set()
    changed = True
    while changed:
        changed = False
        for name, func in idx.items():
            if name in asserts:
                continue
            for n in _iter_own_scope(func.body):
                if isinstance(n, ast.Assert):
                    asserts.add(name)
                    changed = True
                    break
                if isinstance(n, ast.Call):
                    if _is_assertion_call(n):
                        asserts.add(name)
                        changed = True
                        break
                    if isinstance(n.func, ast.Name) and n.func.id in asserts:
                        asserts.add(name)
                        changed = True
                        break
    return frozenset(asserts)


def _is_recognized_assertion(node, helper_asserts: frozenset = frozenset()) -> bool:
    """An `ast.Assert`, a name-recognized assertion-shaped call, or a call to a same-file helper
    function proven (by `_helper_names_that_assert`) to assert internally."""
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        if _is_assertion_call(node):
            return True
        if isinstance(node.func, ast.Name) and node.func.id in helper_asserts:
            return True
    return False


def _has_skip_decorator(func) -> bool:
    for dec in func.decorator_list:
        node = dec.func if isinstance(dec, ast.Call) else dec
        parts: list = []
        while True:
            if isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            elif isinstance(node, ast.Name):
                parts.append(node.id)
                break
            else:
                break
        if "skip" in ".".join(reversed(parts)).lower():
            return True
    return False


def _contains_call(node) -> bool:
    return any(isinstance(n, ast.Call) for n in ast.walk(node))


# ---- sub-pattern 2: literal tautology ------------------------------------------------------------
def _is_tautology(test) -> bool:
    if isinstance(test, ast.Constant) and test.value is True:
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.Is)):
        left_node, right_node = test.left, test.comparators[0]
        if _contains_call(left_node) or _contains_call(right_node):
            return False                     # a Call can return a different value each evaluation
        left = ast.dump(left_node, annotate_fields=False)
        right = ast.dump(right_node, annotate_fields=False)
        return left == right
    return False


# ---- sub-pattern 3: swallowed failure path -------------------------------------------------------
def _no_op_handler_body(handler) -> bool:
    for s in handler.body:
        if isinstance(s, ast.Pass):
            continue
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and (
                s.value.value is Ellipsis or isinstance(s.value.value, str)):
            continue                                          # a docstring/`...`-as-comment: still no-op
        return False
    return True


def _is_broad_exc_name(node) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _BROAD_EXC_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _BROAD_EXC_NAMES
    return False


def _is_broad_handler_type(handler) -> bool:
    t = handler.type
    if t is None:
        return True                                          # bare `except:`
    if isinstance(t, ast.Tuple):
        return any(_is_broad_exc_name(e) for e in t.elts)
    return _is_broad_exc_name(t)


def _try_has_qualifying_handler(try_stmt) -> bool:
    return any(_no_op_handler_body(h) and _is_broad_handler_type(h) for h in try_stmt.handlers)


def _try_body_has_call(try_stmt) -> bool:
    for s in try_stmt.body:
        for n in ast.walk(s):
            if isinstance(n, ast.Call):
                return True
    return False


def _is_swallowed_failure(try_stmt, func_stmts, helper_asserts: frozenset = frozenset()) -> bool:
    if not _try_has_qualifying_handler(try_stmt):
        return False
    if not _try_body_has_call(try_stmt):
        return False
    try_subtree_ids = {id(n) for n in _walk_own_scope(try_stmt)}
    for n in _iter_own_scope(func_stmts):
        if id(n) in try_subtree_ids:
            continue                                          # inside this try's own body: not a "save"
        if _is_recognized_assertion(n, helper_asserts):
            return False                                      # a real assertion survives outside -> safe
    return True


# ---- sub-pattern 4a: a test-shaped function that can never fire independently --------------------
def _iter_nested_defs(stmts):
    """Every `FunctionDef`/`AsyncFunctionDef` reachable from `stmts` by control-flow-only recursion
    (the same discipline `_walk_own_scope` already uses for sub-patterns 1-3) -- i.e., genuinely
    nested one level inside the enclosing function's own body. `_walk_own_scope` stops descending the
    instant it hits ANY nested scope, so this naturally finds each directly-reachable nested def
    without also picking up a def-inside-that-def (out of scope for this sub-pattern; see the
    module docstring)."""
    for s in stmts:
        for n in _walk_own_scope(s):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield n


def _analyze_nested_test_functions(func, helper_asserts: frozenset = frozenset()) -> list:
    findings = []
    for nested in _iter_nested_defs(func.body):
        if not nested.name.startswith("test_"):
            continue
        nested_scope = list(_iter_own_scope(nested.body))
        if any(_is_recognized_assertion(n, helper_asserts) for n in nested_scope):
            findings.append({"line": nested.lineno, "func": nested.name, "kind": "uncollectable_nested"})
    return findings


# ---- sub-pattern 4b: a permanently-true skip guard ------------------------------------------------
def _is_skipif_call(node) -> bool:
    """A Call whose dotted callee's LAST component is `skipif` (case-insensitive) -- covers both
    `pytest.mark.skipif` and `unittest.skipIf`."""
    if not isinstance(node, ast.Call):
        return False
    chain = _callee_chain(node)
    if not chain:
        return False
    return chain.split(".")[-1].lower() == "skipif"


def _decorator_skipif_conditions(func):
    """Yields the condition-expression node of each `skipif`/`skipIf`-shaped decorator on func that
    actually carries a positional condition argument."""
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and _is_skipif_call(dec) and dec.args:
            yield dec, dec.args[0]


def _is_skip_call_stmt(stmt) -> bool:
    """`pytest.skip(...)` as a bare expression statement, or `raise unittest.SkipTest(...)` (any of
    the `SkipTest(...)` call form, or a bare `raise SkipTest`/`raise unittest.SkipTest` name form)."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        chain = _callee_chain(stmt.value)
        return bool(chain) and chain.split(".")[-1].lower() == "skip"
    if isinstance(stmt, ast.Raise):
        exc = stmt.exc
        if isinstance(exc, ast.Call):
            chain = _callee_chain(exc)
            return chain.split(".")[-1] == "SkipTest" if chain else False
        if isinstance(exc, ast.Attribute):
            return exc.attr == "SkipTest"
        if isinstance(exc, ast.Name):
            return exc.id == "SkipTest"
    return False


def _function_body_always_skip_guard(func):
    """The function's FIRST statement, if (and only if) it is `if <cond>: pytest.skip(...)` /
    `if <cond>: raise unittest.SkipTest(...)` -- deliberately shallow (first-statement-only, per the
    mission spec) so this never overreaches into scanning every branch of the function body."""
    if not func.body:
        return None
    first = func.body[0]
    if isinstance(first, ast.If) and any(_is_skip_call_stmt(s) for s in first.body):
        return first
    return None


def _analyze_always_skip(func) -> list:
    findings = []
    for dec, cond in _decorator_skipif_conditions(func):
        if _is_tautology(cond):
            findings.append({"line": dec.lineno, "func": func.name, "kind": "uncollectable_always_skip"})
    guard = _function_body_always_skip_guard(func)
    if guard is not None and _is_tautology(guard.test):
        findings.append({"line": guard.lineno, "func": func.name, "kind": "uncollectable_always_skip"})
    return findings


def _analyze_module_level_always_skip(tree) -> list:
    """A module-level `pytestmark = pytest.mark.skipif(<tautology>, ...)` -- applies to every test in
    the file, so it is anchored at the assignment (not any one test function)."""
    findings = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Call) and _is_skipif_call(value) and value.args and _is_tautology(value.args[0]):
            findings.append({"line": node.lineno, "func": "<module>", "kind": "uncollectable_always_skip"})
    return findings


# ---- per-function analysis ------------------------------------------------------------------------
def _analyze_test_function(func, helper_asserts: frozenset = frozenset()) -> list:
    findings = []
    stmts = func.body
    scope_nodes = list(_iter_own_scope(stmts))

    if not any(_is_recognized_assertion(n, helper_asserts) for n in scope_nodes) \
            and not _has_skip_decorator(func):
        findings.append({"line": func.lineno, "func": func.name, "kind": "no_assertion"})

    for n in scope_nodes:
        if isinstance(n, ast.Assert) and _is_tautology(n.test):
            findings.append({"line": n.lineno, "func": func.name, "kind": "tautology"})

    for n in scope_nodes:
        if isinstance(n, ast.Try) and _is_swallowed_failure(n, stmts, helper_asserts):
            findings.append({"line": n.lineno, "func": func.name, "kind": "swallowed_failure"})

    findings.extend(_analyze_nested_test_functions(func, helper_asserts))
    findings.extend(_analyze_always_skip(func))

    return findings


def analyze_file(src: str, path: str) -> list:
    if not _is_test_filename(path):
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []                                             # fail-open: skip unparseable files
    helper_asserts = _helper_names_that_assert(tree)
    out = []
    for func in _iter_test_functions(tree):
        for f in _analyze_test_function(func, helper_asserts):
            f["file"] = path
            out.append(f)
    for f in _analyze_module_level_always_skip(tree):
        f["file"] = path
        out.append(f)
    return out


# =============================================================================================
# Stop-hook adapter (formerly stopchecks/stopcheck_hollow_test.py)
# =============================================================================================
# _is_scratch/_read (imported at module top from _stdlib_ast_helpers) are shared verbatim with
# deadPureStatement.py (2026-07-09: found alpha-equivalent by AST canonicalization; extracted
# rather than left duplicated -- see tests/test_detector_engines_are_stdlib_isolated.py).


_KIND_MESSAGE = {
    "no_assertion": "test `{func}` (line {line}) contains no assertion of any kind — it passes "
                     "regardless of what the code under test does",
    "tautology": "test `{func}` (line {line}) asserts a tautology (`assert True`, or comparing an "
                 "expression to itself) — it can never fail",
    "swallowed_failure": "test `{func}` (line {line}) wraps its only call-under-test in a try/except "
                          "that silently swallows any failure (broad except, no-op body, no assertion "
                          "elsewhere to catch it)",
    "uncollectable_nested": "`{func}` (line {line}) is a test-shaped function nested inside another "
                             "function's body — pytest's collector never discovers a nested `def`, so "
                             "it can never be independently run, skipped, or reported; only whatever "
                             "calls it can surface its failure",
    "uncollectable_always_skip": "the skip guard on `{func}` (line {line}) has a condition that is "
                                  "provably always true — it can never actually run, so it can never fail",
}


def _allowed(lineno, lines) -> bool:                          # on-the-record override (makoto convention)
    return 1 <= lineno <= len(lines) and "makoto-allow" in lines[lineno - 1].lower()


def _run(ctx) -> list:
    out = []
    # iteration scaffold (touched -> .py -> cwd-anchor -> scratch-skip -> read) shared with
    # deadPureStatement._run via the stdlib-isolated helper home -- 2026-07-09 dedup round 2
    for p, src in iter_touched_python_sources(ctx):
        lines = src.splitlines()
        for f in analyze_file(src, str(p)):
            if _allowed(f["line"], lines):
                continue                                       # exempt, never a fire
            out.append(Finding(
                pattern_id="gate.hollow_test",
                file=str(p),
                line=f["line"],
                level="error",                                # a BLOCKING finding
                message=("hollow test: " + _KIND_MESSAGE[f["kind"]].format(func=f["func"], line=f["line"])
                          + ". A test that cannot fail is not a test; make it assert real behavior or "
                            "remove it; annotate `# makoto-allow: <reason>` only if intentional."),
            ))
    return out


# A Stop gate (fires on the Stop hook, like every gate). Its `fn` is the AST analyzer rather than a
# claim-vs-ledger predicate — mirrors gate.liveness's split exactly. `run` returns list[Finding] (a
# closed test file can have many hollow tests); run_stop_checks normalizes a list like a single finding.
from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.hollow_test", applies_at="Stop", posture="BLOCK", may_block=True, run=_run)
