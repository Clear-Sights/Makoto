"""gate.hollow_test's pure AST analyzer: a HOLLOWED-class detector (SPIRIT.md §4) — a test that
survives in name while its content is gutted. Four independently-firing sub-patterns, each
zero-FP by construction or by corpus measurement (see tests/test_hollow_test_fp.py):

  1. no_assertion       — the test body asserts nothing at all (no `assert`, no assertion-shaped
                           call), and is not an explicitly `@skip`-decorated stub.
  2. tautology           — an `assert` on a statically-truthy literal (`assert True`, `assert 1`,
                           `assert "nonempty"`, `assert not False`), or an `assert x == x` /
                           `assert x is x` where both
                           sides of the comparison are the textually-identical expression AND
                           neither side contains a Call OR an attribute access (a call can return a
                           different object/value on each evaluation — e.g. `assert cache() is
                           cache()` is a genuine memoization/identity check; an attribute read can
                           be a property whose value changes between reads — so neither is flagged;
                           corpus-found FP, see test_gate_shape.py's own
                           `assert load_stopchecks() is load_stopchecks()`).
  3. swallowed_failure   — a `try` around the call-under-test (or around the assertion itself)
                           whose only `except` is both BROAD (bare/`Exception`/`BaseException`)
                           and a no-op, with no assertion anywhere else in the function to catch a
                           failure.
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

The analyzer engine and its Stop-hook adapter live in this ONE flat file (see
docs/adr/0036-hollow-test-single-file-layout.md for the layout history). The analyzer
itself is self-contained (zero imports beyond stdlib `ast`); the `makoto-allow` exemption and the
GateContext plumbing live in the adapter half below — this discipline is unchanged from the split
layout, only the file boundary moved.
"""
from __future__ import annotations
import ast
import os

from makoto.vocab import _MAKOTO_ALLOW_RX
from makoto.substrate._stdlib_ast_helpers import _callee_chain, iter_touched_python_sources
from makoto.vocab import Finding

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
    """Yields every function/async-function whose name starts with `test_` (pytest's
    `python_functions` convention) that is reachable from module level WITHOUT crossing a function
    boundary — i.e. also inside a module-level `if`/`try`/`with`/`for`/`while` block (pytest
    collects those normally) and inside a class at any class-nesting depth. For a class whose name
    starts with `Test` AND whose base list textually includes something containing `TestCase`
    (unittest style), a bare `test`-prefixed method name (no underscore) also counts."""
    blocks = [ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While,
              ast.ExceptHandler]
    if hasattr(ast, "TryStar"):
        blocks.append(ast.TryStar)
    if hasattr(ast, "match_case"):
        blocks.extend([ast.Match, ast.match_case])
    blocks = tuple(blocks)

    def _from_class(cls_node):
        is_unittest = cls_node.name.startswith("Test") and _bases_are_unittest_style(cls_node)
        for child in cls_node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name.startswith("test_"):
                    yield child
                elif is_unittest and child.name.startswith("test"):
                    yield child
            elif isinstance(child, ast.ClassDef):
                yield from _from_class(child)
            elif isinstance(child, blocks):
                yield from _walk(ast.iter_child_nodes(child))

    def _walk(nodes):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    yield node
            elif isinstance(node, ast.ClassDef):
                yield from _from_class(node)
            elif isinstance(node, blocks):
                yield from _walk(ast.iter_child_nodes(node))

    yield from _walk(ast.iter_child_nodes(tree))


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
# _callee_chain is imported at module top from _stdlib_ast_helpers, the stdlib-isolated shared
# helper home (see tests/test_detector_engines_are_stdlib_isolated.py, and
# docs/adr/0038-stdlib-ast-helper-extraction.md for the extraction history).
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
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("self", "cls")
                and node.func.attr in helper_asserts):
            return True                                   # unittest-style `self._helper()` chain
    return False


def _local_helper_index(tree):
    """name -> FunctionDef/AsyncFunctionDef node, for every module-level function PLUS every
    method of a module-level class (any class-nesting depth) — the latter so the standard
    unittest `self._helper()` assert-helper resolves (nested defs stay excluded). A same-file,
    name-resolved fact only — never a general call-graph solver, and never crossing file
    boundaries; a name collision resolves to the LAST definition, which is FN-safe (it can only
    suppress a fire, never add one)."""
    idx = {}

    def _collect(nodes):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                idx[node.name] = node
            elif isinstance(node, ast.ClassDef):
                _collect(node.body)

    _collect(ast.iter_child_nodes(tree))
    return idx


def _helper_names_that_assert(tree) -> frozenset:
    """Names of module-level helper functions whose own body (transitively, through calls to other
    same-file module-level helpers) contains a recognized assertion. Extends the recognizer to the
    extremely common 'shared assert helper' pattern (a test's only observable check is a call to a
    same-file helper like `_clean(call)` / `_assert_ok(x)` that itself does `assert not x.fired`) --
    corpus-found FP class (assay's test_forbidden_location.py). Generous/FN-safe by construction:
    it can only make a sub-pattern fire LESS, never more. Each body is walked exactly ONCE, into
    (does it assert directly?, which bare names does it call?); the fixpoint then closes over that
    finite, already-extracted call graph, so it always terminates."""
    asserts: set = set()
    calls: dict = {}
    for name, func in _local_helper_index(tree).items():
        called: set = set()
        for n in _iter_own_scope(func.body):
            if _is_recognized_assertion(n):
                asserts.add(name)
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    called.add(n.func.id)
                elif (isinstance(n.func, ast.Attribute)
                        and isinstance(n.func.value, ast.Name)
                        and n.func.value.id in ("self", "cls")):
                    called.add(n.func.attr)               # method-to-method helper chain
        calls[name] = called
    changed = True
    while changed:
        changed = False
        for name, called in calls.items():
            if name not in asserts and called & asserts:
                asserts.add(name)
                changed = True
    return frozenset(asserts)


def _imported_helper_names_that_assert(tree, path: str) -> frozenset:
    """Names imported from a SIBLING module whose definition there asserts.

    `_helper_names_that_assert` is deliberately same-file, which leaves one FP class uncovered:
    the SHARED plant-and-restore helper. A "can this check fail" test whose whole body is
    `smoke_replace(self, path, old, new, ...)` -- where the imported helper plants a fault,
    asserts the named test goes red, restores it, and asserts byte-identity -- reads as
    no_assertion and fires. Measured: it fired on all three of Gyroscope's teeth tests, each of
    which asserts four times inside that helper. A gate that fires on the very tests written to
    prove other tests can fail is exactly the shape that gets the gate switched off.

    ONE hop, and only to a module resolvable next to this file: the sibling's own same-file
    transitive closure counts, but the sibling's imports are NOT followed, so this stays a
    name-resolved fact and never becomes a call-graph solver. Any failure to resolve, read or
    parse adds NOTHING and leaves the finding exactly as it was -- the same FN-safe direction as
    the same-file index, since these names can only make a sub-pattern fire less.
    """
    names: set = set()
    here = os.path.dirname(os.path.abspath(path))
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        wanted = {a.name: (a.asname or a.name) for a in node.names if a.name != "*"}
        parts = (node.module or "").split(".") if node.module else []
        if not wanted or not parts:
            continue
        roots = []
        if node.level:                                    # from .plant_support import smoke_replace
            root = here
            for _ in range(node.level - 1):
                root = os.path.dirname(root)
            roots.append(root)
        else:                                             # from tests.plant_support import ...
            root = here
            for _ in range(5):                            # bounded: never an unbounded walk to /
                roots.append(root)
                parent = os.path.dirname(root)
                if parent == root:
                    break
                root = parent
        for root in roots:
            candidate = os.path.join(root, *parts) + ".py"
            if not os.path.isfile(candidate):
                continue
            try:
                with open(candidate, encoding="utf-8", errors="replace") as fh:
                    sibling = ast.parse(fh.read())
            except (OSError, SyntaxError, ValueError):
                break                                     # unreadable/unparseable: add nothing
            asserting = _helper_names_that_assert(sibling)
            for original, local in wanted.items():
                if original in asserting:
                    names.add(local)
            break
    return frozenset(names)


def _has_skip_decorator(func) -> bool:
    """True iff some decorator's FINAL dotted-name component is exactly a skip-family callable
    (case-insensitive `skip`/`skipif`/`skipunless`/`skiptest`) -- `@pytest.mark.skip`,
    `@unittest.skipIf(...)`, a bare `@skip`. A name that merely CONTAINS the substring `skip`
    (`@with_skiplist`) is some other decorator and must not silently disable sub-pattern 1."""
    for dec in func.decorator_list:
        node = dec.func if isinstance(dec, ast.Call) else dec
        parts: list = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        if parts and parts[0].lower() in ("skip", "skipif", "skipunless", "skiptest"):
            return True
    return False


def _contains_call(node) -> bool:
    return any(isinstance(n, ast.Call) for n in ast.walk(node))


# ---- sub-pattern 2: literal tautology ------------------------------------------------------------
def _is_tautology(test) -> bool:
    def _literal_truth(node):
        """bool(<literal>) when the truth value is statically decidable, else None. Covers every
        `ast.literal_eval`-able display (`1`, `"nonempty"`, `[1]`, `(0,)`) plus `not <literal>`."""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = _literal_truth(node.operand)
            return None if inner is None else (not inner)
        try:
            return bool(ast.literal_eval(node))
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return None                                   # not a literal: truth unknown
    if _literal_truth(test) is True:
        return True                                       # a statically-truthy literal always passes
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.Is)):
        left_node, right_node = test.left, test.comparators[0]

        def _may_dispatch(n):
            # a Call can return a different value each evaluation; an Attribute read can be a
            # property whose value changes between reads (`assert self.n == self.n`)
            return any(isinstance(x, (ast.Call, ast.Attribute)) for x in ast.walk(n))

        if _may_dispatch(left_node) or _may_dispatch(right_node):
            return False
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
    return any(_contains_call(s) for s in try_stmt.body)


def _is_swallowed_failure(try_stmt, func_stmts, helper_asserts: frozenset = frozenset()) -> bool:
    if not _try_has_qualifying_handler(try_stmt):
        return False
    # the try body must contain something that can FAIL: a call under test, or an assertion the
    # broad no-op handler would swallow (`try: assert x == 5 / except Exception: pass`)
    if not _try_body_has_call(try_stmt) and not any(
            isinstance(n, ast.Assert) for s in try_stmt.body for n in _walk_own_scope(s)):
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
    for n in _iter_own_scope(stmts):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n


def _analyze_nested_test_functions(func, helper_asserts: frozenset = frozenset()) -> list:
    findings = []
    for nested in _iter_nested_defs(func.body):
        if not nested.name.startswith("test_"):
            continue
        if any(_is_recognized_assertion(n, helper_asserts) for n in _iter_own_scope(nested.body)):
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
    actually carries a condition — positional, or the `condition=` keyword spelling
    (`@pytest.mark.skipif(condition=True, ...)`)."""
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and _is_skipif_call(dec):
            cond = dec.args[0] if dec.args else next(
                (kw.value for kw in dec.keywords if kw.arg == "condition"), None)
            if cond is not None:
                yield dec, cond


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
    """The function's FIRST statement (ignoring a leading docstring, which is documentation, not
    a statement), if (and only if) it is `if <cond>: pytest.skip(...)` /
    `if <cond>: raise unittest.SkipTest(...)` -- deliberately shallow (first-statement-only, per the
    mission spec) so this never overreaches into scanning every branch of the function body."""
    body = func.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]                                   # a docstring is documentation, not a statement
    if not body:
        return None
    first = body[0]
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
        marks = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        for mark in marks:                                # `pytestmark = [pytest.mark.skipif(...)]`
            if not (isinstance(mark, ast.Call) and _is_skipif_call(mark)):
                continue
            cond = mark.args[0] if mark.args else next(
                (kw.value for kw in mark.keywords if kw.arg == "condition"), None)
            if cond is not None and _is_tautology(cond):
                findings.append({"line": node.lineno, "func": "<module>", "kind": "uncollectable_always_skip"})
    return findings


# ---- per-function analysis ------------------------------------------------------------------------
def _analyze_test_function(func, helper_asserts: frozenset = frozenset()) -> list:
    findings = []
    stmts = func.body
    scope_nodes = list(_iter_own_scope(stmts))
    nested_findings = _analyze_nested_test_functions(func, helper_asserts)

    # ONE construct, ONE fire: when the only "assertion" lives in an uncollectable nested test
    # def, the specific uncollectable_nested finding below already blocks — stacking a second
    # no_assertion fire on the enclosing function would demand two `makoto-allow` lines to clear
    # one construct.
    if not any(_is_recognized_assertion(n, helper_asserts) for n in scope_nodes) \
            and not _has_skip_decorator(func) and not nested_findings:
        findings.append({"line": func.lineno, "func": func.name, "kind": "no_assertion"})

    for n in scope_nodes:
        if isinstance(n, ast.Assert) and _is_tautology(n.test):
            findings.append({"line": n.lineno, "func": func.name, "kind": "tautology"})

    for n in scope_nodes:
        if isinstance(n, ast.Try) and _is_swallowed_failure(n, stmts, helper_asserts):
            findings.append({"line": n.lineno, "func": func.name, "kind": "swallowed_failure"})

    findings.extend(nested_findings)
    findings.extend(_analyze_always_skip(func))

    return findings


def analyze_file(src: str, path: str) -> list:
    if not _is_test_filename(path):
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []                                             # fail-open: skip unparseable files
    helper_asserts = (_helper_names_that_assert(tree)
                      | _imported_helper_names_that_assert(tree, path))
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
# deadPureStatement.py -- see tests/test_detector_engines_are_stdlib_isolated.py, and
# docs/adr/0038-stdlib-ast-helper-extraction.md for the extraction history.


_KIND_MESSAGE = {
    "no_assertion": "test `{func}` (line {line}) contains no assertion of any kind — it cannot "
                     "detect wrong results; only an unhandled exception in the code it calls can "
                     "ever fail it",
    "tautology": "test `{func}` (line {line}) asserts a tautology (a statically-truthy literal "
                 "like `assert True`, or comparing an expression to itself) — it pins no actual "
                 "behavior of the code under test",
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


def _allowed(lineno, lines) -> bool:
    """On-the-record override (makoto convention), via the ONE canonical marker predicate.

    The marker is recognized by `makoto_allowed`/`_MAKOTO_ALLOW_RX` (§7.5b, the predicate every
    factory-built content check uses), which requires a colon and a NON-EMPTY reason — matching
    this module's own finding text ("annotate `# makoto-allow: <reason>`") and the rule makoto
    installs into the user's CLAUDE.md ("an on-the-record, auditable rationale, never a
    disguise"). One concept, one predicate: the marker means the same thing everywhere it is
    honored, so an exemption asserting an audit trail can never be accepted without one.
    (`makoto.vocab` is already on this engine's isolation allowlist — see
    tests/test_detector_engines_are_stdlib_isolated.py.)
    See docs/adr/0037-hollow-test-makoto-allow-predicate.md for the decision history."""
    return 1 <= lineno <= len(lines) and _MAKOTO_ALLOW_RX.search(lines[lineno - 1]) is not None


def _run(ctx) -> list:
    out = []
    # iteration scaffold (touched -> .py -> cwd-anchor -> scratch-skip -> read) shared with
    # deadPureStatement._run via the stdlib-isolated helper home
    for p, src in iter_touched_python_sources(ctx.touched, getattr(ctx, "cwd", None), ctx.fs_read):
        lines = src.splitlines()
        if _is_test_filename(str(p)):
            # A test file that does not parse cannot be analyzed OR collected: absence of
            # findings over it would be vacuous, not clean. This is a decision input (the very
            # corpus this gate rules on), not a transport failure, so it must not fail open the
            # way an unreadable file does — report it instead of silently skipping it.
            try:
                ast.parse(src)
            except SyntaxError as e:
                bad_line = e.lineno or 1
                if not _allowed(bad_line, lines):
                    out.append(Finding(
                        pattern_id="gate.hollow_test",
                        file=str(p),
                        line=bad_line,
                        level="error",
                        message=(f"hollow test scan impossible: test file does not parse "
                                 f"(SyntaxError near line {bad_line}), so none of its tests can "
                                 "be collected or evaluated — fix the syntax error, or annotate "
                                 "`# makoto-allow: <reason>` on that line only if intentional."),
                    ))
                continue
        for f in analyze_file(src, str(p)):
            if _allowed(f["line"], lines):
                continue                                       # exempt, never a fire
            out.append(Finding(
                pattern_id="gate.hollow_test",
                file=str(p),
                line=f["line"],
                level="error",                                # a BLOCKING finding
                message=("hollow test: " + _KIND_MESSAGE[f["kind"]].format(func=f["func"], line=f["line"])
                          + ". A test that cannot catch a failure is not a test; make it assert real "
                            "behavior or remove it; annotate `# makoto-allow: <reason>` only if "
                            "intentional."),
            ))
    return out


# A Stop gate (fires on the Stop hook, like every gate). Its `fn` is the AST analyzer rather than a
# claim-vs-ledger predicate — mirrors gate.liveness's split exactly. `run` returns list[Finding] (a
# closed test file can have many hollow tests); run_stop_checks normalizes a list like a single finding.
from makoto.registry import Check as _Check
CHECK = _Check(id="gate.hollow_test", applies_at="Stop", posture="BLOCK", may_block=True, run=_run,
               eats=frozenset({"touched", "cwd", "fs_read"}), tests="PATTERN_MATCH")
