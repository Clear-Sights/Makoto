"""pattern 1.31 predicate — JWT 'none' algorithm in a decode allow-list (alg-confusion bypass).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, a jwt/jose ``decode``
call whose ``algorithms=`` allow-list contains the unsigned ``"none"`` algorithm:
  * ``jwt.decode(token, key, algorithms=["none"])``
  * ``jwt.decode(token, algorithms=["HS256", "none"])``   (mixed — 'none' still whitelisted)
  * case-insensitive: ``"NONE"`` / ``"None"`` (PyJWT historically matched the alg case-insensitively).

Materiality: the JWT ``none`` algorithm means "no signature"; whitelisting it in ``decode``'s
``algorithms`` makes decode ACCEPT a forged/unsigned token while it still "succeeds" — the classic
alg-confusion auth bypass (CWE-347; PyJWT CVE-2022-29217). This is DISTINCT from 1.28: there
verification is switched off (``verify=False`` / ``options={verify_signature: False}``); here
verification is nominally ON but the allow-list whitelists the no-signature algorithm — a different
AST node (a literal list on the ``algorithms`` kwarg). 1.28's docstring explicitly declares this
variant out of its scope and names 1.31 as the home for it.

Reuses the proven ``lexicons.JWT_CALLEE_RX`` + ``lib.factories.callee_chain`` jwt/jose callee gate (so a
non-jwt ``decode`` whose ``algorithms`` list contains ``"none"`` — e.g. a compression layer where
``"none"`` means "no compression" — stays silent), and ``lib.factories.ast_introduced_predicate`` for the
active-code AST gate (a comment/string MENTION never fires). A legitimate case (a test decoding a
deliberately-unsigned token) is annotated ``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) a non-literal ``algorithms`` (``algorithms=algs`` / built dynamically) is
not a literal list at the call site -> not matched. (b) the ENCODE side (``jwt.encode(..., algorithm=
"none")``, signing an unsigned token) is a different shape, out of this verifier-path pattern's scope
(mirrors 1.28). (c) an aliased ``from jwt import decode; decode(t, algorithms=["none"])`` has no jwt
token in the callee chain -> not matched (FN-safe; an FP on an honest non-jwt ``decode`` is the binding harm).

Knight-Leveson: stdlib ast/re only.
"""
from __future__ import annotations
import ast
from typing import Optional

from makoto.lib.factories import ast_introduced_predicate, callee_chain
from makoto.lexicons import JWT_CALLEE_RX

from makoto.lexicons import _PY_FILE_RX as _TARGET_RX


def _is_none_alg(node) -> bool:
    """True iff `node` is a string Constant whose value is the unsigned `none` algorithm (any case)."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower() == "none"


def _algorithms_whitelists_none(value) -> bool:
    """True iff the `algorithms=` value is a literal list/tuple/set containing a 'none' alg string."""
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return False
    return any(_is_none_alg(elt) for elt in value.elts)


def _jwt_none_node_match(node: ast.AST) -> Optional[str]:
    if not isinstance(node, ast.Call):
        return None
    chain = callee_chain(node)
    if not JWT_CALLEE_RX.search(chain):
        return None
    # only the `decode` entry point verifies a signature; encode/other calls are out of scope.
    if chain.split(".")[-1] != "decode":
        return None
    for kw in node.keywords:
        if kw.arg == "algorithms" and _algorithms_whitelists_none(kw.value):
            return 'algorithms=["none"]'
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_jwt_none_node_match)
