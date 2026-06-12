"""pattern 1.27 predicate — verifier NEUTERED (body hollowed, or a broad except swallows the failure).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, on the constitution integrity-check
surface (`constitution/integrity/checks/[^/]+\\.py$` — the exact path 1.1 anchors on), a check
that exists and "passes" but performs no real verification:

  (A) HOLLOW BODY — a verifier-named ``FunctionDef`` whose ENTIRE body (after an optional docstring)
      is one neutering statement: ``return <truthy-const>`` / ``pass`` / ``assert <truthy-const>``
      (the assert-True arm added 2026-06-02, harvest Phase 1 / family C-core).
  (B) SWALLOWED EXCEPTION — a BROAD except clause (bare ``except:`` / ``except Exception`` /
      ``except BaseException``) whose body swallows the failure into a pass (``pass`` /
      ``return <truthy-const>``). The runtime sibling of body-hollowing (harvest Phase 1 / family F).

It is the deletion / short-circuit cousin of 1.1 (which catches a loosened COMPARATOR but, per the
recovery refuter, NOT a wholesale-hollow body — 1.1's body_rx requires startswith/endswith/re.match/
in[], none present here). So 1.27 is non-redundant and material on the same surface.

FP-safety: (a) the NARROW path anchor excludes ordinary permissive base-class / null-object
``return True`` methods — they live off the integrity-check path. NOTE (harvest VF-2): this path is
near-dead in the honest corpus (2/1335 writes, both makoto's own fixtures), so corpus-FP=0 here is
an UNDERPOWERED null, not earned discrimination — FP-safety rests on (b)–(e). (b) the verifier-NAME
gate excludes trivial helpers / dunders. (c) the broad-except gate excludes a SPECIFIC-typed except
(``except ImportError`` / a named degrade-open) — honest narrowing never fires. (d) the active-code
AST gate (``lib.factories.parse_introduced``) means a comment / docstring / string MENTION never fires.
(e) ``makoto-allow: <reason>`` exempts an intentional trivially-true base / documented degrade-open.

Prior art (static analysis): the swallow arm mirrors bandit B110 (try_except_pass) / ruff S110 /
CodeQL py/empty-except; no mainstream rule targets ``assert True``-as-sole-check, the gap the
assert arm fills. Knight-Leveson: stdlib ast/re only.
"""
from __future__ import annotations
import ast
import re
from typing import Optional

from makoto.lib.factories import ast_introduced_predicate

_TARGET_RX = re.compile(r"constitution/integrity/checks/[^/]+\.py$")
# a verifier-named function: the name contains an integrity/verification verb. Narrow context
# (the integrity-checks dir) makes these names load-bearing rather than generic.
_VERIFIER_NAME_RX = re.compile(r"(?i)(verif|valid|integrit|attest|check|ensure|enforce|assert)")


def _is_truthy_const(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is not None and bool(node.value) is True


def _swallows(stmt) -> bool:
    """One statement that NEUTERS a check — converts a failure into a pass: `pass`,
    `return <truthy-const>`, or `assert <truthy-const>` (a tautological always-pass assertion)."""
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Return) and _is_truthy_const(stmt.value):
        return True
    return isinstance(stmt, ast.Assert) and _is_truthy_const(stmt.test)


def _single_effective(body) -> Optional[ast.stmt]:
    """The body's single statement after dropping a leading docstring, else None."""
    b = list(body)
    if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
            and isinstance(b[0].value.value, str):
        b = b[1:]
    return b[0] if len(b) == 1 else None


def _hollow_body(fn) -> bool:
    """True iff the function body (post-docstring) is exactly one neutering statement —
    `pass` / `return <truthy-const>` / `assert <truthy-const>` (an always-pass / do-nothing check)."""
    stmt = _single_effective(fn.body)
    return stmt is not None and _swallows(stmt)


_BROAD_EXCEPT = frozenset({"Exception", "BaseException"})


def _broad_except(handler: ast.ExceptHandler) -> bool:
    """True iff the clause catches EVERYTHING — bare `except:` or `except Exception/BaseException`
    (incl. in a tuple). A SPECIFIC type (`ImportError`, `HSMUnavailable`, …) is honest narrowing,
    NOT failure-masking, so it is excluded — the primary FP firewall for the swallow arm (a
    degrade-open around an EXPECTED-unavailable dependency does not fire)."""
    t = handler.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    return any(isinstance(n, ast.Name) and n.id in _BROAD_EXCEPT for n in names)


def _hollow_node_match(node: ast.AST) -> Optional[str]:
    # (original + assert-True arm) a verifier-named function NEUTERED to a single
    # pass / return-truthy / assert-truthy statement.
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
            and _VERIFIER_NAME_RX.search(node.name) and _hollow_body(node):
        return f"def {node.name}() -> hollow"
    # (swallowed-exception arm) a BROAD except handler whose body swallows the failure into a pass —
    # the runtime sibling of body-hollowing. Broad-only + the integrity-path anchor + makoto-allow
    # carry FP-safety; a specific-typed except (honest narrowing) never fires.
    if isinstance(node, ast.ExceptHandler) and _broad_except(node):
        stmt = _single_effective(node.body)
        if stmt is not None and _swallows(stmt):
            return "broad except -> swallow"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_hollow_node_match)
