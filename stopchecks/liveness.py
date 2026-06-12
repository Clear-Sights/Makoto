from __future__ import annotations
import ast

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
