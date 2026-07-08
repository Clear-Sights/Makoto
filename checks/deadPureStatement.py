"""gate.liveness's pure AST analyzer + its Stop-hook adapter (SPEC-5 Task 4, owner-revised
layout: formerly `stopchecks/liveness.py` + `stopchecks/stopcheck_liveness.py`, combined into one
flat file here — same single-file choice as `hollowTest.py`/`canonTimeoutRecur.py`; see
`hollowTest.py`'s module docstring for the rationale). The gate id (`gate.liveness`), `.run(ctx)`
contract, and `GateContext` are UNCHANGED — only the file/import path moved.

The analyzer detects ILLUSORY statements: provably pure computations whose result never reaches
I/O or a live binding (dead code shaped like work). Self-contained like `hollowTest.py`: zero
imports beyond stdlib `ast`.
"""
from __future__ import annotations
import ast
import os
import tempfile
from pathlib import Path

from makoto.checks._shared import StopCheck
from makoto.schema import Finding

_PURE_BUILTINS = frozenset(
    "len str int float bool tuple list dict set frozenset abs min max sum "
    "ord chr hash round isinstance type sorted reversed".split())
_PURE_BINOP = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
               ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd)
_PURE_UNARY = (ast.UAdd, ast.USub, ast.Invert, ast.Not)


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
    comprehension) or leaked by a walrus — such locals are live regardless of straight-line use."""
    captured = set()
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
              ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
    for child in ast.iter_child_nodes(func):
        for n in ast.walk(child):
            if isinstance(n, nested):
                for inner in ast.walk(n):
                    if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
                        captured.add(inner.id)
            if isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
                captured.add(n.target.id)                   # walrus leak
    return captured


def live_locals(func) -> set:
    """Locals whose value reaches an output. Fixpoint over a conservative seed set."""
    escaping = _escaping_names(func)
    locals_ = {a.arg for a in func.args.args} | {a.arg for a in getattr(func.args, 'kwonlyargs', [])}
    body = list(ast.walk(func))
    live = set(captured_locals(func))                       # captured locals are live
    # seed: names read by returns/yields, by effect statements, and inside try/with bodies
    seeds = []
    for n in body:
        if isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom)) and getattr(n, "value", None) is not None:
            seeds.append(n.value)
        # A `raise X from Y` is an OUTPUT: the raised value (and cause) escapes the function, so every
        # name it reads is live. Without this seed an exception accumulator (`last_exc = None` … then
        # `raise RuntimeError(last_exc)`) had its None-init flagged dead — a false positive.
        if isinstance(n, ast.Raise):
            if n.exc is not None:
                seeds.append(n.exc)
            if n.cause is not None:
                seeds.append(n.cause)
    for stmt in ast.walk(func):
        if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr)):
            if is_effect(stmt, locals_, escaping):
                seeds.append(stmt)
        if isinstance(stmt, (ast.Try, ast.With, ast.AsyncWith)):
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
    assigns = [(s, _assigned_name(s)) for s in ast.walk(func)
               if _assigned_name(s) is not None]
    # Tuple/list-unpack assigns (`tool, pattern = sample_patterns[i]`) have no single _assigned_name,
    # so the plain fixpoint never propagated their RHS reads. If ANY unpacked target is live, the RHS
    # value reaches a live binding, so its reads are live too. Gated on a live target (not seeded
    # unconditionally) so a genuinely-dead feeder of UNUSED unpack targets still fires — no FN.
    unpacks = [(s, _unpack_target_names(s)) for s in ast.walk(func)
               if _unpack_target_names(s)]
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
    names = {a.arg for a in func.args.args} | {a.arg for a in getattr(func.args, 'kwonlyargs', [])}
    names |= {a.arg for a in getattr(func.args, 'posonlyargs', [])}
    if func.args.vararg:
        names.add(func.args.vararg.arg)
    if func.args.kwarg:
        names.add(func.args.kwarg.arg)
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    def _walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                names.add(child.id)
            if isinstance(child, ast.arg):
                names.add(child.arg)
            if not isinstance(child, nested):
                _walk(child)
    for stmt in func.body:
        _walk(stmt)
    return names


def _typed_locals(func, locals_) -> set:
    """Locals provably holding a builtin-typed value at EVERY binding: a name is typed only if it has
    at least one binding and ALL of its bindings are a single-target Assign/AnnAssign whose RHS is
    builtin-typed (given the locals proven so far). Monotone fixpoint. A NAME proven typed lets a
    downstream `a + 1` be recognised as builtin-typed (so a dead constant chain is fully flagged),
    while a bare parameter — never assigned here — and any name with even one non-typed/aliasing/aug
    binding stays untyped (operator-overload-safe; conservative, soundness over recall).

    Disqualifiers (force untyped): a parameter binding, an AugAssign, a for/with/comprehension target,
    a tuple/attr/subscript store, or an Assign whose RHS is not provably builtin-typed."""
    # Collect, per name, the RHS of every clean single-target Assign/AnnAssign, and a disqualified set.
    good = {}           # name -> list of RHS nodes (all must end up builtin-typed)
    disqualified = set()
    for a in func.args.args + getattr(func.args, 'kwonlyargs', []) + getattr(func.args, 'posonlyargs', []):
        disqualified.add(a.arg)                                  # a parameter's type is unknown
    if func.args.vararg:
        disqualified.add(func.args.vararg.arg)
    if func.args.kwarg:
        disqualified.add(func.args.kwarg.arg)
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
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
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            disqualified.add(node.target.id)                    # walrus value unknown
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, nested):
                _visit(child)
    for stmt in func.body:
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
    """Statements that are provably pure, not effects, and whose result never reaches I/O."""
    escaping = _escaping_names(func)
    locals_ = _local_names(func)
    typed = _typed_locals(func, locals_)
    live = live_locals(func)
    captured = captured_locals(func)
    out = []
    for stmt in func.body:
        _scan(stmt, func, locals_, escaping, typed, live, captured, out)
    return out


def _scan(stmt, func, locals_, escaping, typed, live, captured, out):
    # Recurse into EVERY nested block (present-closure / block-containment model). Liveness is
    # function-global, so a pure unused value is dead inside a loop too. Nested def/lambda/class are
    # SEPARATE scopes -> skipped (analyze_file walks them as their own FunctionDefs). try/with-body
    # assigns are already in `live` (live_locals seeds them) so they are never flagged here.
    if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        name = _assigned_name(stmt)
        rhs = stmt.value
        if (rhs is not None and is_pure(rhs, locals_, typed) and not is_effect(stmt, locals_, escaping)
                and name is not None and name not in live and name not in captured):
            out.append(stmt)
        elif name is None and isinstance(stmt, ast.Assign):
            # No single-Name target -> a TUPLE/LIST/CHAINED-target assign (`a, b = 1, 2`; `a = b = 5`;
            # `[a, b] = [1, 2]`; `(x,) = (1+2,)`). Without this branch every-name-dead unpacks were a
            # silent FN. Flag dead iff: the RHS is pure, the stmt is not an effect (an attr/subscript
            # store target IS an effect via is_effect, so those are excluded), there is at least one
            # bound Store Name, and EVERY bound name is dead AND uncaptured — any one live/captured
            # target keeps the whole binding live. (is_pure/is_effect/live/captured reused verbatim.)
            names = {n.id for t in stmt.targets for n in ast.walk(t)
                     if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            if (names and is_pure(rhs, locals_, typed) and not is_effect(stmt, locals_, escaping)
                    and all(nm not in live and nm not in captured for nm in names)):
                out.append(stmt)
    elif isinstance(stmt, ast.Expr):
        # A bare LITERAL statement is not illusory WORK: a string Constant is a docstring / block
        # comment (material as __doc__), `...` is an intentional stub placeholder, a bare number is a
        # no-op — none is a computation shaped like work. The genuine target is a discarded
        # COMPUTATION (`x + 1`, `len(items)` on a typed local). So exclude bare Constants.
        if (not isinstance(stmt.value, ast.Constant)
                and is_pure(stmt.value, locals_, typed) and not is_effect(stmt, locals_, escaping)):
            out.append(stmt)                                # bare pure computation: illusory
    elif isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
        for s in (*stmt.body, *getattr(stmt, "orelse", [])):
            _scan(s, func, locals_, escaping, typed, live, captured, out)
    elif isinstance(stmt, ast.Try):
        for s in (*stmt.body, *[b for h in stmt.handlers for b in h.body],
                  *stmt.orelse, *stmt.finalbody):
            _scan(s, func, locals_, escaping, typed, live, captured, out)
    elif isinstance(stmt, ast.Match):
        # Descend into each case body — a dead pure statement inside a `match` arm is still dead.
        for case in stmt.cases:
            for s in case.body:
                _scan(s, func, locals_, escaping, typed, live, captured, out)
    # ast.FunctionDef / AsyncFunctionDef / Lambda / ClassDef: separate scopes, NOT scanned here.


def analyze_file(src: str, path: str) -> list:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []                                           # fail-open: skip unparseable files
    lines = src.splitlines()
    def _allowed(lineno):                                   # on-the-record override (makoto convention)
        return 1 <= lineno <= len(lines) and "makoto-allow" in lines[lineno - 1].lower()
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in illusory_statements(node):
                if _allowed(stmt.lineno):
                    continue                                # exempt, never a fire
                out.append({"file": path, "line": stmt.lineno, "func": node.name})
    return out


# =============================================================================================
# Stop-hook adapter (formerly stopchecks/stopcheck_liveness.py)
# =============================================================================================
def _scratch_roots() -> tuple[str, ...]:
    roots = []
    for d in (tempfile.gettempdir(), "/tmp", "/var/folders", os.path.expanduser("~/.claude")):
        try:
            roots.append(os.path.realpath(d))
        except OSError:
            pass
    return tuple(roots)


_SCRATCH_ROOTS = _scratch_roots()


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _is_scratch(p, cwd) -> bool:
    """A touched .py is out-of-scope scratch iff cwd is KNOWN, the file is NOT inside that working
    dir, AND it lives under a known temp/scratch root. A file under cwd is the closed unit under
    construction (this is how pytest tmp fixtures and real project files appear) and always counts;
    only stray scratch OUTSIDE the working project (e.g. /tmp/mining/*, the live-session
    contamination vector) is skipped. This realizes "a block counts only when opened AND closed" at
    the unit-closure layer: the analyzer's detection logic is untouched, the firing scope narrows to
    closed work. Suppression requires a known cwd AND a scratch root -- never a blanket skip -- so an
    unknown working dir keeps the gate's full teeth and a real (non-temp) file always fires."""
    if not cwd:
        return False                                         # working dir unknown -> never suppress (FN-safe)
    rp = os.path.realpath(str(p))
    if _under(rp, os.path.realpath(str(cwd))):
        return False                                         # inside the working dir -> in scope
    return any(_under(rp, r) for r in _SCRATCH_ROOTS)        # outside cwd AND in a scratch root -> stray scratch


def _read(ctx, p):
    fn = getattr(ctx, "fs_read", None)
    return fn(p) if callable(fn) else Path(p).read_text(encoding="utf-8")


def _run(ctx) -> list:
    out = []
    cwd = getattr(ctx, "cwd", None)
    for p in getattr(ctx, "touched", ()):
        if not str(p).endswith(".py"):
            continue
        # anchor a possibly-relative touched key to the event's OWN cwd, never the dispatch
        # process's ambient one (matches _dispatch.py's real fs_read/fs_exists join)
        real_p = p if not cwd or os.path.isabs(str(p)) else os.path.join(cwd, p)
        if _is_scratch(real_p, cwd):
            continue                                         # stray scratch outside the working project -> not a closed unit
        try:
            src = _read(ctx, real_p)
        except OSError:
            continue
        if not isinstance(src, str):
            continue                                         # fs_read miss (None) -> skip, never crash
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
GATE = StopCheck(id="gate.liveness", fn=analyze_file, run=_run)


from makoto.checks._loader import Check as _Check
CHECK = _Check(id="gate.liveness", applies_at="Stop", posture="BLOCK", run=GATE.run)
