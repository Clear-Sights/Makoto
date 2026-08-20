"""gate.liveness's pure AST analyzer + its Stop-hook adapter (SPEC-5 Task 4, owner-revised
layout: formerly `stopchecks/liveness.py` + `stopchecks/stopcheck_liveness.py`, combined into one
flat file here — same single-file choice as `hollowTest.py`/`canonTimeoutRecur.py`; see
`hollowTest.py`'s module docstring for the rationale). The gate id (`gate.liveness`), `.run(ctx)`
contract, and `GateContext` are UNCHANGED — only the file/import path moved.

The analyzer detects ILLUSORY statements: provably pure computations whose result never reaches
I/O or a live binding (dead code shaped like work). Import-isolated like `hollowTest.py`: stdlib
`ast` plus the whitelisted makoto substrate only (`makoto.vocab`,
`makoto.substrate._stdlib_ast_helpers`, `makoto.registry` — the exact contract
tests/test_detector_engines_are_stdlib_isolated.py enforces).
"""
from __future__ import annotations
import ast

from makoto.vocab import _MAKOTO_ALLOW_RX
from makoto.substrate._stdlib_ast_helpers import iter_touched_python_sources
from makoto.vocab import Finding

_PURE_BUILTINS = frozenset(
    "len str int float bool tuple list dict set frozenset abs min max sum "
    "ord chr hash round isinstance type sorted reversed".split())
_PURE_BINOP = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
               ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd)
_PURE_UNARY = (ast.UAdd, ast.USub, ast.Invert, ast.Not)
# `except*` (ast.TryStar, 3.11+) carries the same body/handlers/orelse/finalbody shape as ast.Try
# and must be walked identically — a statement under `except*` is not invisible.
_TRY_STMTS = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)
# The actual callables behind _PURE_BUILTINS (no import needed — builtins are in scope), for the
# guarded constant-argument evaluation in `_scan`: a whitelisted call/arithmetic over literals
# that RAISES (`int('abc')`, `1 // 0`, `min([])`) is an observable effect, not a removable no-op.
_BUILTIN_FNS = {f.__name__: f for f in (
    len, str, int, float, bool, tuple, list, dict, set, frozenset, abs, min, max, sum,
    ord, chr, hash, round, isinstance, type, sorted, reversed)}


def _builtin_typed(node, typed_locals=frozenset()) -> bool:
    """Provably evaluates to a builtin type, so an operator on it cannot dispatch to a user dunder.
    `typed_locals` are locals proven (by `_typed_locals`) to hold a builtin-typed value; a plain
    parameter is NEVER in that set (its type is unknown), which keeps the operator-overload hole shut."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return node.id in typed_locals
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_builtin_typed(e, typed_locals) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_builtin_typed(k, typed_locals) and _builtin_typed(v, typed_locals)
                   for k, v in zip(node.keys, node.values) if k is not None)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _PURE_UNARY):
        return _builtin_typed(node.operand, typed_locals)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _PURE_BINOP):
        return _builtin_typed(node.left, typed_locals) and _builtin_typed(node.right, typed_locals)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _PURE_BUILTINS and not node.keywords:
        return all(_builtin_typed(a, typed_locals) for a in node.args)
    return False


def is_pure(node, local_names, typed_locals=frozenset()) -> bool:
    """Conservative: True only if evaluating `node` provably cannot have a side effect."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return node.id in local_names                       # local read only (global read => FN-safe)
    if isinstance(node, ast.BoolOp):
        return all(is_pure(v, local_names, typed_locals) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _PURE_UNARY):
        return is_pure(node.operand, local_names, typed_locals) and _builtin_typed(node.operand, typed_locals)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _PURE_BINOP):
        return (is_pure(node.left, local_names, typed_locals) and is_pure(node.right, local_names, typed_locals)
                and _builtin_typed(node.left, typed_locals) and _builtin_typed(node.right, typed_locals))
    if isinstance(node, ast.Compare):
        ops = [node.left, *node.comparators]
        return all(is_pure(o, local_names, typed_locals) and _builtin_typed(o, typed_locals) for o in ops)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _PURE_BUILTINS and not node.keywords:
        # A whitelisted builtin still dispatches to a USER dunder on a non-builtin operand
        # (len->__len__, min/sorted->__lt__, sum->__add__, abs->__abs__, ...). So a builtin
        # call is pure only when every argument is provably builtin-typed, exactly as for
        # operators above — otherwise the operand's dunder could carry a side effect.
        return all(is_pure(a, local_names, typed_locals) and _builtin_typed(a, typed_locals)
                   for a in node.args)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(is_pure(e, local_names, typed_locals) for e in node.elts)
    return False                                            # everything else: impure (conservative)


def is_effect(stmt, local_names, escaping_names) -> bool:
    """A statement that may affect the world outside its own pure value (always live)."""
    for n in ast.walk(stmt):
        if isinstance(n, ast.Await):
            return True
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name)
                                            and n.func.id in _PURE_BUILTINS and not n.keywords):
            return True                                     # call to anything not whitelisted-pure
    targets = []
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)):
        targets = [stmt.target]
    for t in targets:
        for n in ast.walk(t):
            if isinstance(n, (ast.Attribute, ast.Subscript)):
                return True                                 # store escapes via __setattr__/__setitem__
            if isinstance(n, ast.Name) and n.id in escaping_names:
                return True                                 # assignment to a global/nonlocal name
    return False


def _names_read(node) -> set:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _assigned_name(stmt):
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        return stmt.targets[0].id
    if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)) and isinstance(stmt.target, ast.Name):
        return stmt.target.id
    return None


def _unpack_target_names(stmt) -> set:
    """Names bound by a TUPLE/LIST/STARRED unpack assignment target (`a, b = ...`, `a, *rest = ...`).
    Empty for a single-Name / attr / subscript target — those are handled by `_assigned_name`. Used by
    the liveness fixpoint to propagate: if ANY unpacked name is live, the RHS reads are live too."""
    if not isinstance(stmt, ast.Assign):
        return set()
    out = set()
    for t in stmt.targets:
        if isinstance(t, (ast.Tuple, ast.List)):
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    out.add(n.id)
    return out


def _escaping_names(func) -> set:
    out = set()
    for n in ast.walk(func):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
    return out


def captured_locals(func) -> set:
    """Names of the function's own locals that are referenced by a NESTED scope (closure/lambda/
    comprehension/class body) or leaked by a walrus — such locals are live regardless of
    straight-line use. `ast.ClassDef` counts: a class body executes in its own scope but READS the
    enclosing function's locals (`class C: y = x`), so removing `x = 1` raises NameError."""
    captured = set()
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
              ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
    for n in ast.walk(func):
        if n is func:
            continue                                        # func itself is a `nested` type, not a nested scope
        if isinstance(n, nested):
            for inner in ast.walk(n):
                if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
                    captured.add(inner.id)
        if isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
            captured.add(n.target.id)                       # walrus leak
    return captured


def live_locals(func) -> set:
    """Locals whose value reaches an output. Fixpoint over a conservative seed set."""
    escaping = _escaping_names(func)
    locals_ = {a.arg for a in func.args.args} | {a.arg for a in getattr(func.args, 'kwonlyargs', [])}
    live = set(captured_locals(func))                       # captured locals are live
    # seed: names read by returns/yields, by effect statements, and inside try/with bodies
    seeds = []
    for stmt in ast.walk(func):
        if isinstance(stmt, (ast.Return, ast.Yield, ast.YieldFrom)) and getattr(stmt, "value", None) is not None:
            seeds.append(stmt.value)
        # A `raise X from Y` is an OUTPUT: the raised value (and cause) escapes the function, so every
        # name it reads is live. Without this seed an exception accumulator (`last_exc = None` … then
        # `raise RuntimeError(last_exc)`) had its None-init flagged dead — a false positive.
        if isinstance(stmt, ast.Raise):
            if stmt.exc is not None:
                seeds.append(stmt.exc)
            if stmt.cause is not None:
                seeds.append(stmt.cause)
        if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr)) \
                and is_effect(stmt, locals_, escaping):
            seeds.append(stmt)
        if isinstance(stmt, _TRY_STMTS + (ast.With, ast.AsyncWith)):
            for s in stmt.body:
                nm = _assigned_name(s)
                if nm:
                    live.add(nm)                            # try/with conservatism
        # Consuming / control-flow positions: a name read in a test, iterable, context-expr, assert,
        # or comprehension genuinely USES its value (it steers execution or is consumed) even when that
        # value never reaches a return. Seeding these closes the "flag/counter read only in a while/if/
        # for condition" FP class. An augmented target (`x += ...`) READS x. Over-seeding is FN-safe
        # (more live => fewer flags), never an FP.
        if isinstance(stmt, (ast.If, ast.While)):
            seeds.append(stmt.test)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            seeds.append(stmt.iter)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            for it in stmt.items:
                seeds.append(it.context_expr)
        elif isinstance(stmt, ast.Assert):
            seeds.append(stmt.test)
            if stmt.msg is not None:
                seeds.append(stmt.msg)
        elif isinstance(stmt, ast.Match):
            # `match subject: case ... if guard:` CONSUMES the subject (it steers which case runs)
            # and each guard, exactly like an `if`/`while` test. Without seeding these, a local read
            # ONLY by a match was flagged dead — a false positive (`if status == 2:` was correctly
            # silent, `match status:` was not). Over-seeding is FN-safe (more live => fewer flags).
            seeds.append(stmt.subject)
            for case in stmt.cases:
                if case.guard is not None:
                    seeds.append(case.guard)
        elif isinstance(stmt, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for g in stmt.generators:
                seeds.append(g.iter)
                seeds.extend(g.ifs)
        elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            live.add(stmt.target.id)                        # `x += ...` reads x
    for s in seeds:
        live |= _names_read(s)
    # fixpoint: if a live local is assigned from expr, the names that expr reads become live
    changed = True
    # Tuple/list-unpack assigns (`tool, pattern = sample_patterns[i]`) have no single _assigned_name,
    # so the plain fixpoint never propagated their RHS reads. If ANY unpacked target is live, the RHS
    # value reaches a live binding, so its reads are live too. Gated on a live target (not seeded
    # unconditionally) so a genuinely-dead feeder of UNUSED unpack targets still fires — no FN.
    assigns, unpacks = [], []
    for s in ast.walk(func):
        name = _assigned_name(s)
        if name is not None:
            assigns.append((s, name))
        unpacked = _unpack_target_names(s)
        if unpacked:
            unpacks.append((s, unpacked))
    while changed:
        changed = False
        for stmt, name in assigns:
            if name in live:
                rhs = stmt.value if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)) else None
                if rhs is not None:
                    new = _names_read(rhs) - live
                    if new:
                        live |= new
                        changed = True
        for stmt, names in unpacks:
            if names & live and stmt.value is not None:
                new = _names_read(stmt.value) - live
                if new:
                    live |= new
                    changed = True
    return live


def _local_names(func) -> set:
    """Every name bound in THIS function scope: params + kwonly + any name assigned in its body
    (excluding nested-scope bodies). A read of such a name is pure (reading a local has no effect);
    operator-dispatch impurity is handled separately by `_builtin_typed`/`_typed_locals`."""
    names = {a.arg for a in (func.args.args + getattr(func.args, 'kwonlyargs', [])
                             + getattr(func.args, 'posonlyargs', []))}
    if func.args.vararg:
        names.add(func.args.vararg.arg)
    if func.args.kwarg:
        names.add(func.args.kwarg.arg)
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    def _walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, nested):
                continue                    # a nested scope's bindings are NOT this function's locals
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                names.add(child.id)
            if isinstance(child, ast.arg):
                names.add(child.arg)
            _walk(child)
    for stmt in func.body:
        if not isinstance(stmt, nested):    # a top-of-body nested def/class is a nested scope too
            _walk(stmt)
    return names


def _typed_locals(func) -> set:
    """Locals provably holding a builtin-typed value at EVERY binding: a name is typed only if it has
    at least one binding and ALL of its bindings are a single-target Assign/AnnAssign whose RHS is
    builtin-typed (given the locals proven so far). Monotone fixpoint. A NAME proven typed lets a
    downstream `a + 1` be recognised as builtin-typed (so a dead constant chain is fully flagged),
    while a bare parameter — never assigned here — and any name with even one non-typed/aliasing/aug
    binding stays untyped (operator-overload-safe; conservative, soundness over recall).

    Disqualifiers (force untyped): a parameter binding, an AugAssign, a for/with-as/except-as
    target, a name declared `global`/`nonlocal` anywhere in the function (including a nonlocal
    rebind inside a nested scope), a tuple/attr/subscript store, or an Assign whose RHS is not
    provably builtin-typed."""
    # Collect, per name, the RHS of every clean single-target Assign/AnnAssign, and a disqualified set.
    good = {}           # name -> list of RHS nodes (all must end up builtin-typed)
    disqualified = set()
    for a in func.args.args + getattr(func.args, 'kwonlyargs', []) + getattr(func.args, 'posonlyargs', []):
        disqualified.add(a.arg)                                  # a parameter's type is unknown
    if func.args.vararg:
        disqualified.add(func.args.vararg.arg)
    if func.args.kwarg:
        disqualified.add(func.args.kwarg.arg)
    # a `global`/`nonlocal` name — declared HERE, or rebound from any nested scope `_visit` skips —
    # can hold anything at any time, so it is never provably builtin-typed
    disqualified.update(_escaping_names(func))
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    def _visit(node):
        if isinstance(node, ast.Assign):
            nm = _assigned_name(node)
            if nm is not None:
                good.setdefault(nm, []).append(node.value)
            else:                                               # tuple/attr/subscript target
                for t in node.targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                            disqualified.add(n.id)
        elif isinstance(node, ast.AnnAssign):
            nm = _assigned_name(node)
            if nm is not None and node.value is not None:
                good.setdefault(nm, []).append(node.value)
            elif isinstance(node.target, ast.Name):
                disqualified.add(node.target.id)                # bare annotation / non-name target
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                disqualified.add(node.target.id)                # += may dispatch __iadd__
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    disqualified.add(n.id)                      # loop var type unknown
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    for n in ast.walk(item.optional_vars):
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                            disqualified.add(n.id)              # `with cm as v`: __enter__ result
        elif isinstance(node, ast.ExceptHandler) and node.name:
            disqualified.add(node.name)                         # `except E as v`: exception object
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            disqualified.add(node.target.id)                    # walrus value unknown
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, nested):
                _visit(child)
    for stmt in func.body:
        if not isinstance(stmt, nested):    # a top-of-body nested def/class is a separate scope
            _visit(stmt)
    # Fixpoint: a name is typed once ALL its good RHS are builtin-typed and it is not disqualified.
    typed = set()
    changed = True
    while changed:
        changed = False
        for name, rhss in good.items():
            if name in typed or name in disqualified:
                continue
            if rhss and all(_builtin_typed(rhs, typed) for rhs in rhss):
                typed.add(name)
                changed = True
    return typed


def illusory_statements(func) -> list:
    """Statements that are provably pure, not effects, and whose result never reaches I/O.

    `first_bind` maps each local to the smallest line number of any binding of it (params bind at
    entry, i.e. line 0). `_scan` uses it as a flow guard: a local READ at or before its first
    binding line (`z = x + 1` then `x = 5`) raises UnboundLocalError when evaluated, so the
    statement is not provably pure and is never flagged — line-based, hence conservative in loops
    (suppression only, FN-safe)."""
    escaping = _escaping_names(func)
    locals_ = _local_names(func)
    typed = _typed_locals(func)
    live = live_locals(func)
    captured = captured_locals(func)
    first_bind = {}
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

    def _note(name, lineno):
        if name not in first_bind or lineno < first_bind[name]:
            first_bind[name] = lineno

    for a in (func.args.args + getattr(func.args, "kwonlyargs", [])
              + getattr(func.args, "posonlyargs", [])):
        _note(a.arg, 0)                                     # a parameter is bound at entry
    if func.args.vararg:
        _note(func.args.vararg.arg, 0)
    if func.args.kwarg:
        _note(func.args.kwarg.arg, 0)
    for nm in escaping:
        _note(nm, 0)                                        # global/nonlocal: bound elsewhere

    def _bindings(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, nested):
                if not isinstance(child, ast.Lambda):       # a lambda binds no name of its own
                    _note(child.name, child.lineno)         # the def/class NAME is a binding here
                continue                                    # ...but its body is a separate scope
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                _note(child.id, child.lineno)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                _note(child.name, child.lineno)
            elif isinstance(child, ast.arg):
                _note(child.arg, child.lineno)
            _bindings(child)

    for stmt in func.body:
        if isinstance(stmt, nested):
            if not isinstance(stmt, ast.Lambda):
                _note(stmt.name, stmt.lineno)
        else:
            _bindings(stmt)
    out = []
    for stmt in func.body:
        _scan(stmt, locals_, escaping, typed, live, captured, first_bind, out)
    return out


def _scan(stmt, locals_, escaping, typed, live, captured, first_bind, out):
    # Recurse into EVERY nested block (present-closure / block-containment model). Liveness is
    # function-global, so a pure unused value is dead inside a loop too. Nested def/lambda/class are
    # SEPARATE scopes -> skipped (analyze_file walks them as their own FunctionDefs). try/with-body
    # assigns are already in `live` (live_locals seeds them) so they are never flagged here.
    def _flow_unproven(node):
        # a local read AT or BEFORE its first binding line raises UnboundLocalError when
        # evaluated -> the statement is NOT provably pure (see illusory_statements' docstring)
        return any(first_bind.get(nm, 0) >= stmt.lineno
                   for nm in _names_read(node) if nm in locals_)

    def _statically_raises(node):
        # A whitelisted-pure expression over LITERALS that raises when evaluated (`int('abc')`,
        # `1 // 0`, `min([])`) has an observable effect — raising — so "provably cannot have a
        # side effect" would be a false fact and removal would change behaviour. Only literal
        # operands are ever evaluated, so the probe is bounded by the source text itself.
        for n in ast.walk(node):
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                try:
                    l, r = ast.literal_eval(n.left), ast.literal_eval(n.right)
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                    continue                                # non-literal operand: not evaluated
                try:
                    (l / r) if isinstance(n.op, ast.Div) else                         (l // r) if isinstance(n.op, ast.FloorDiv) else (l % r)
                except Exception:
                    return True
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name)                     and n.func.id in _BUILTIN_FNS and not n.keywords                     and not any(isinstance(a, ast.Starred) for a in n.args):
                try:
                    args = [ast.literal_eval(a) for a in n.args]
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                    continue                                # non-literal argument: not evaluated
                try:
                    _BUILTIN_FNS[n.func.id](*args)
                except Exception:
                    return True
        return False

    if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        rhs = stmt.value
        if rhs is None or not is_pure(rhs, locals_, typed) or is_effect(stmt, locals_, escaping):
            return                                          # impure / effectful / bare annotation
        if _flow_unproven(rhs) or _statically_raises(rhs):
            return                                          # evaluating it can raise: not removable
        # Which names does this binding bind? A single-Name target is the common case; anything else
        # is a TUPLE/LIST/CHAINED-target assign (`a, b = 1, 2`; `a = b = 5`; `[a, b] = [1, 2]`;
        # `(x,) = (1+2,)`) — without those every-name-dead unpacks were a silent FN. (An attr/
        # subscript store target IS an effect via is_effect, so it already returned above.)
        name = _assigned_name(stmt)
        if name is not None:
            bound = {name}
        elif isinstance(stmt, ast.Assign):
            bound = {n.id for t in stmt.targets for n in ast.walk(t)
                     if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        else:
            bound = set()                                   # AnnAssign/AugAssign on a non-Name target
        # Dead iff there is at least one bound name and EVERY one is dead AND uncaptured — any single
        # live/captured target keeps the whole binding live.
        if bound and all(nm not in live and nm not in captured for nm in bound):
            out.append(stmt)
    elif isinstance(stmt, ast.Expr):
        # A bare LITERAL statement is not illusory WORK: a string Constant is a docstring / block
        # comment (material as __doc__), `...` is an intentional stub placeholder, a bare number is a
        # no-op — none is a computation shaped like work. The genuine target is a discarded
        # COMPUTATION (`x + 1`, `len(items)` on a typed local). So exclude bare Constants.
        if (not isinstance(stmt.value, ast.Constant)
                and is_pure(stmt.value, locals_, typed) and not is_effect(stmt, locals_, escaping)
                and not _flow_unproven(stmt.value) and not _statically_raises(stmt.value)):
            out.append(stmt)                                # bare pure computation: illusory
    elif isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
        for s in (*stmt.body, *getattr(stmt, "orelse", [])):
            _scan(s, locals_, escaping, typed, live, captured, first_bind, out)
    elif isinstance(stmt, _TRY_STMTS):
        # ast.TryStar (`except*`) carries the identical statement shape — walked identically, so
        # a dead pure statement under `except*` is exactly as visible as under plain `except`.
        for s in (*stmt.body, *[b for h in stmt.handlers for b in h.body],
                  *stmt.orelse, *stmt.finalbody):
            _scan(s, locals_, escaping, typed, live, captured, first_bind, out)
    elif isinstance(stmt, ast.Match):
        # Descend into each case body — a dead pure statement inside a `match` arm is still dead.
        for case in stmt.cases:
            for s in case.body:
                _scan(s, locals_, escaping, typed, live, captured, first_bind, out)
    # ast.FunctionDef / AsyncFunctionDef / Lambda / ClassDef: separate scopes, NOT scanned here.


def analyze_file(src: str, path: str) -> list:
    try:
        tree = ast.parse(src)
    except (SyntaxError, RecursionError):
        return []                                           # fail-open: skip unparseable files
    lines = src.splitlines()
    # Redact every string-literal span before the marker scan: an exemption asserts an on-the-
    # record audit trail, which only a COMMENT provides — a `makoto-allow:` sequence INSIDE a
    # string literal (`z = len('see makoto-allow: the docs')`) is data, not a rationale, and must
    # not exempt. Offsets are utf-8 byte columns (ast's own unit), hence the encode/decode hop.
    redacted = [ln.encode("utf-8") for ln in lines]
    for node in ast.walk(tree):
        if not ((isinstance(node, ast.Constant) and isinstance(node.value, str))
                or isinstance(node, ast.JoinedStr)):
            continue
        a, b = getattr(node, "lineno", None), getattr(node, "end_lineno", None)
        if a is None or b is None:
            continue
        for li in range(a, b + 1):
            if not 1 <= li <= len(redacted):
                continue
            raw = redacted[li - 1]
            start = max(0, node.col_offset) if li == a else 0
            end = min(len(raw), max(0, node.end_col_offset)) if li == b else len(raw)
            if start < end:
                redacted[li - 1] = raw[:start] + b" " * (end - start) + raw[end:]
    redacted = [b.decode("utf-8", "replace") for b in redacted]

    def _allowed(stmt):
        # On-the-record override via the ONE canonical marker predicate (§7.5b): a reasonless
        # `# makoto-allow` does NOT exempt, matching what this check's own finding text already
        # tells the author to write. An exemption marker asserts an audit trail; accepting one
        # without a rationale accepts the assertion unmeasured. The marker is honored on ANY
        # line of the statement's own span, so a multi-line statement's closing-line annotation
        # (`)  # makoto-allow: ...`) exempts exactly like a single-line one.
        # See docs/adr/0026-liveness-allow-marker-strictness.md for the decision history.
        a = getattr(stmt, "lineno", 0)
        b = getattr(stmt, "end_lineno", None) or a
        return any(1 <= li <= len(redacted)
                   and _MAKOTO_ALLOW_RX.search(redacted[li - 1]) is not None
                   for li in range(a, b + 1))
    out = []
    try:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for stmt in illusory_statements(node):
                    if _allowed(stmt):
                        continue                            # exempt, never a fire
                    out.append({"file": path, "line": stmt.lineno, "func": node.name})
    except RecursionError:
        return []       # carriage-shaped input (pathologically deep expression): fail open,
                        # exactly like the unparseable-file branch above — never a Stop-hook crash
    return out


# =============================================================================================
# Stop-hook adapter (formerly stopchecks/stopcheck_liveness.py)
# =============================================================================================
# The iteration scaffold (iter_touched_python_sources, imported from _stdlib_ast_helpers) is shared with
# hollowTest.py (2026-07-09: found alpha-equivalent by AST canonicalization; extracted rather than
# left duplicated -- the stdlib-only helper module preserves the same import-graph-isolation
# property both detectors need, enforced by tests/test_detector_engines_are_stdlib_isolated.py).


def _run(ctx) -> list:
    out = []
    # iteration scaffold (touched -> .py -> cwd-anchor -> scratch-skip -> read) shared with
    # hollowTest._run via the stdlib-isolated helper home -- 2026-07-09 dedup round 2
    for p, src in iter_touched_python_sources(ctx.touched, getattr(ctx, "cwd", None), ctx.fs_read):
        for f in analyze_file(src, str(p)):
            out.append(Finding(
                pattern_id="gate.liveness",
                file=str(p),
                line=f["line"],
                level="error",                               # a BLOCKING finding
                message=(f"illusory code: {f['func']} line {f['line']} is pure and never reaches I/O. "
                         f"Make it material (use its result / give it an effect) or remove it before this "
                         f"is complete; annotate `# makoto-allow: <reason>` only if it is intentional."),
            ))
    return out


# A Stop gate (fires on the Stop hook, like every gate). Its `fn` is the AST analyzer rather than a
# claim-vs-ledger predicate, so its teeth are audited BEHAVIORALLY (the soundness/FP suite +
# test_dispatch_liveness_gate_blocks), not by falsify's single-fn mutation harness — see
# scripts/falsify._BEHAVIORAL_TEETH. `run` returns list[Finding] (a closed unit can have many
# illusory statements); run_stop_checks normalizes a list exactly like a single finding.
from makoto.registry import Check as _Check
CHECK = _Check(id="gate.liveness", applies_at="Stop", posture="BLOCK", may_block=True, run=_run,
               eats=frozenset({"touched", "cwd", "fs_read"}), tests="PATTERN_MATCH")
