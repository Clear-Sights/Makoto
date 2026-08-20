"""content.verifier_body_hollowed predicate — verifier NEUTERED (body hollowed, or a broad except swallows the failure).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, on the constitution integrity-check
surface (`constitution/integrity/checks/[^/]+\\.py$` — the exact path content.verifier_predicate_weakened anchors on), a check
that exists and "passes" but performs no real verification:

  (A) HOLLOW BODY — a verifier-named ``FunctionDef`` whose ENTIRE body (after an optional docstring)
      is one neutering statement: ``return <truthy-const>`` / ``pass`` / ``assert <truthy-const>``
      (the assert-True arm added 2026-06-02, harvest Phase 1 / family C-core).
  (B) SWALLOWED EXCEPTION — a BROAD except clause (bare ``except:`` / ``except Exception`` /
      ``except BaseException``) whose body swallows the failure into a pass (``pass`` /
      ``return <truthy-const>``). The runtime sibling of body-hollowing (harvest Phase 1 / family F).

It is the deletion / short-circuit cousin of content.verifier_predicate_weakened (which catches a loosened COMPARATOR but, per the
recovery refuter, NOT a wholesale-hollow body — content.verifier_predicate_weakened's body_rx requires startswith/endswith/re.match/
in[], none present here). So content.verifier_body_hollowed is non-redundant and material on the same surface.

FP-safety: (a) the NARROW path anchor excludes ordinary permissive base-class / null-object
``return True`` methods — they live off the integrity-check path. NOTE (harvest VF-2): this path is
near-dead in the honest corpus (2/1335 writes, both makoto's own fixtures), so corpus-FP=0 here is
an UNDERPOWERED null, not earned discrimination — FP-safety rests on (b)–(e). (b) the verifier-NAME
gate excludes trivial helpers / dunders. (c) the broad-except gate excludes a SPECIFIC-typed except
(``except ImportError`` / a named degrade-open) — honest narrowing never fires. (d) the active-code
AST gate (``substrate.factories.parse_introduced``) means a comment / docstring / string MENTION never fires.
(e) ``makoto-allow: <reason>`` exempts an intentional trivially-true base / documented degrade-open.

Prior art (static analysis): the swallow arm mirrors bandit B110 (try_except_pass) / ruff S110 /
CodeQL py/empty-except; no mainstream rule targets ``assert True``-as-sole-check, the gap the
assert arm fills. Knight-Leveson: stdlib ast/re only.
"""
# See docs/adr/0035-jscpd-clone-flag-verifications.md for why this module's jscpd clone flag
# against certVerifyDisabled.py was verified and dismissed (only shared span is the standard
# predicate-module docstring/import header, no logic in common).
# tests/test_no_alpha_duplicate_functions.py is the package's real duplicate-logic gate.
from __future__ import annotations
import ast
import re
from typing import Optional

from makoto.kit import ast_introduced_predicate

# `[/\\]` + `.+`: the anchor covers the whole surface it claims — nested
# `…/checks/sub/seal.py` and a backslash-delivered Windows path both stayed silent under the
# old `constitution/integrity/checks/[^/]+\.py$`.
_TARGET_RX = re.compile(r"constitution[/\\]integrity[/\\]checks[/\\].+\.py$")
# a verifier-named function: the name contains an integrity/verification verb, or IS a generic
# entry-point name (`run`/`main`, anchored; `predicate`/`probe`/`scan`/`seal` substrings) —
# gutting the dispatch function of an integrity check was invisible under the verb list alone.
# Narrow context (the integrity-checks dir) makes these names load-bearing rather than generic.
_VERIFIER_NAME_RX = re.compile(
    r"(?i)(verif|valid|integrit|attest|check|ensure|enforce|assert|predicate|probe|scan|seal|^run$|^main$)")
_BROAD_EXCEPT = frozenset({"Exception", "BaseException"})


def _is_truthy_const(node) -> bool:
    """True iff `node` is a literal constant that is TRUTHY (`True` / `1` / a non-empty literal).
    `None` and every falsy literal are excluded — `bool(None)` is already False."""
    return isinstance(node, ast.Constant) and bool(node.value)


def _is_tautology(node) -> bool:
    """True iff `node` is an ALWAYS-TRUTHY expression: a truthy literal, `not <falsy-const>`,
    `bool(<truthy-const>)`, or a comparison whose two sides are the same expression under
    `==`/`is`/`<=`/`>=` (`1 == 1`, `s == s`). The literal-constant-only test let trivially
    tautological returns/asserts pass as real checking."""
    if _is_truthy_const(node):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) \
            and isinstance(node.operand, ast.Constant) and not node.operand.value:
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool" \
            and len(node.args) == 1 and not node.keywords and _is_truthy_const(node.args[0]):
        return True
    if isinstance(node, ast.Compare) and len(node.comparators) == 1 \
            and all(isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)) for op in node.ops) \
            and ast.dump(node.left) == ast.dump(node.comparators[0]):
        return True
    return False


def _swallows(stmt) -> bool:
    """One statement that NEUTERS a check — converts a failure into a pass: `pass`, a bare
    `...` ellipsis stub (the no-op `hollowTest.py` already treats as one), `return <tautology>`,
    or `assert <tautology>` (an always-pass assertion)."""
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
            and stmt.value.value is Ellipsis:
        return True
    if isinstance(stmt, ast.Return) and _is_tautology(stmt.value):
        return True
    return isinstance(stmt, ast.Assert) and _is_tautology(stmt.test)


def _post_docstring(body):
    """`body` minus a leading docstring statement."""
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _hollow_body(body) -> bool:
    """True iff `body` (post-docstring) is exactly one neutering statement — `pass` / `...` /
    `return <tautology>` / `assert <tautology>` — or is EMPTY after the docstring (a
    docstring-only body checks exactly as much as `pass` does). Shared by both arms: a hollowed
    function body and a swallowing except-handler body."""
    b = _post_docstring(body)
    if not b:
        return True                      # docstring-only: zero effective statements
    return len(b) == 1 and _swallows(b[0])


def _broad_except(handler: ast.ExceptHandler) -> bool:
    """True iff the clause catches EVERYTHING — bare `except:` or `except Exception/BaseException`
    (incl. in a tuple). A SPECIFIC type (`ImportError`, `HSMUnavailable`, …) is honest narrowing,
    NOT failure-masking, so it is excluded — the primary FP firewall for the swallow arm (a
    degrade-open around an EXPECTED-unavailable dependency does not fire)."""
    t = handler.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    # The `Attribute` form (`except builtins.Exception:`) is the same broad catch spelled
    # qualified — `checks/hollowTest.py:_is_broad_exc_name` already recognizes it; only
    # recognizing `ast.Name` here read an attribute-qualified broad catch as honest narrowing.
    return any(
        (isinstance(n, ast.Name) and n.id in _BROAD_EXCEPT)
        or (isinstance(n, ast.Attribute) and n.attr in _BROAD_EXCEPT)
        for n in names)


def _hollow_node_match(node: ast.AST) -> Optional[str]:
    # (original + assert-True arm) a verifier-named function NEUTERED to a single
    # pass / return-truthy / assert-truthy statement.
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
            and _VERIFIER_NAME_RX.search(node.name) and _hollow_body(node.body):
        return f"def {node.name}() -> hollow"
    # (swallowed-exception arm) a BROAD except handler whose body swallows the failure into a pass —
    # the runtime sibling of body-hollowing. Broad-only + the integrity-path anchor + makoto-allow
    # carry FP-safety; a specific-typed except (honest narrowing) never fires.
    if isinstance(node, ast.ExceptHandler) and _broad_except(node) and _hollow_body(node.body):
        return "broad except -> swallow"
    # (lambda arm) a hollowed verifier BOUND as a lambda (`verify_seal = lambda s: True`) is an
    # `ast.Assign`, not a `FunctionDef` — it was never examined, so the binding form evaded both
    # arms wholesale.
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda) \
            and _is_tautology(node.value.body):
        for t in node.targets:
            if isinstance(t, ast.Name) and _VERIFIER_NAME_RX.search(t.id):
                return f"{t.id} = lambda -> hollow"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_hollow_node_match)


from makoto.registry import Check as _Check
RETRY_HINT = "Don't neuter a verifier on the integrity-check surface: gutting its body to `return True`/`pass`/`assert True`, or wrapping it in a broad `except Exception: pass`/`return True` that swallows the failure, makes a check that 'exists' but never verifies (the wholesale cousin of loosening a comparator, content.verifier_predicate_weakened). Implement the real check; catch the SPECIFIC expected exception, not a bare/`Exception` swallow; if a trivially-true base or a documented degrade-open is genuinely intended, annotate `makoto-allow: <reason>`."
DESCRIPTION = 'verifier neutered — body hollowed (return-True/pass/assert-True) or a broad except swallows the failure, on the integrity-check surface'

CHECK = _Check(id='content.verifier_body_hollowed', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('constitution/integrity/checks', 'except', 'assert True'), retry_hint=RETRY_HINT, description=DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="PATTERN_MATCH")
