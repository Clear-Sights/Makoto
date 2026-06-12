"""pattern 1.28 predicate — JWT signature verification DISABLED (active-code only).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, a disable of
JWT signature verification on a jwt/jose ``decode`` call:
  * ``jwt.decode(token, ..., verify=False)``                          (PyJWT legacy kwarg)
  * ``jwt.decode(token, ..., options={"verify_signature": False})``   (PyJWT options dict)

Materiality: a JWT's signature IS the integrity check that the token is authentic and
untampered. ``verify=False`` / ``verify_signature: False`` makes ``decode`` accept ANY token —
including a forged one — while it still "succeeds": a real verifier silently neutered, the
classic auth bypass. This is the jwt case 1.26 deliberately punts (1.26's TLS callee gate
excludes jwt on purpose); here the SAME ``verify=False`` / options shape is matched ONLY when a
jwt/jose token sits in the call's callee chain, so the keyword is unambiguously the JWT
signature switch and not some unrelated ``verify`` kwarg (``form.clean(verify=False)`` etc.).

Active-code only (lib.factories.parse_introduced): a comment / string / docstring that merely MENTIONS
the shape never fires (an illusory word). A genuinely-legitimate case (a test fixture decoding an
unsigned token on purpose) is annotated ``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) an aliased import (``from jwt import decode; decode(t, verify=False)``)
has no jwt token in the callee chain -> not matched (FN-safe; for a BLOCKING gate an FP on an
honest non-jwt ``decode(verify=False)`` is the binding harm). (b) an ``options`` dict built
dynamically (``opts = {...}; jwt.decode(t, options=opts)``) or via ``dict(verify_signature=False)``
is not a literal Dict at the call site -> not matched. (c) the ``algorithms=["none"]`` alg-confusion
variant is a DIFFERENT shape, out of this pattern's honest scope.

Knight-Leveson: stdlib ast/re only.
"""
from __future__ import annotations
import ast
from typing import Optional

from makoto.lib.factories import ast_introduced_predicate, callee_chain, is_false_const
from makoto.lexicons import JWT_CALLEE_RX

from makoto.lexicons import _PY_FILE_RX as _TARGET_RX
# CALLEE GATE (shared via lexicons.JWT_CALLEE_RX, also used by 1.32): the bare keyword `verify=False`
# is not jwt-specific, so (mirroring 1.26's TLS gate) it only fires when the call's CALLEE chain names
# a JWT library/namespace, BOUNDARY-delimited so `myjwthelper` does not match.


def _options_disables_signature(value) -> bool:
    """True iff `value` is a literal dict carrying `"verify_signature": False` (PyJWT options)."""
    if not isinstance(value, ast.Dict):
        return False
    for k, v in zip(value.keys, value.values):
        if isinstance(k, ast.Constant) and k.value == "verify_signature" and is_false_const(v):
            return True
    return False


def _jwt_node_match(node: ast.AST) -> Optional[str]:
    if not isinstance(node, ast.Call):
        return None
    chain = callee_chain(node)
    if not JWT_CALLEE_RX.search(chain):
        return None
    # only the `decode` entry point verifies a signature; encode/other calls are out of scope.
    if chain.split(".")[-1] != "decode":
        return None
    for kw in node.keywords:
        if kw.arg == "verify" and is_false_const(kw.value):
            return "verify=False"
        if kw.arg == "options" and _options_disables_signature(kw.value):
            return 'options={"verify_signature": False}'
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_jwt_node_match)
