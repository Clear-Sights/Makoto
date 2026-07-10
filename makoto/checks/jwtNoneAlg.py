"""content.jwt_none_alg predicate — JWT 'none' algorithm in a decode allow-list (alg-confusion bypass).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, a jwt/jose ``decode``
call whose ``algorithms=`` allow-list contains the unsigned ``"none"`` algorithm:
  * ``jwt.decode(token, key, algorithms=["none"])``
  * ``jwt.decode(token, algorithms=["HS256", "none"])``   (mixed — 'none' still whitelisted)
  * case-insensitive: ``"NONE"`` / ``"None"`` (PyJWT historically matched the alg case-insensitively).

Materiality: the JWT ``none`` algorithm means "no signature"; whitelisting it in ``decode``'s
``algorithms`` makes decode ACCEPT a forged/unsigned token while it still "succeeds" — the classic
alg-confusion auth bypass (CWE-347; PyJWT CVE-2022-29217). This is DISTINCT from content.jwt_signature_disabled: there
verification is switched off (``verify=False`` / ``options={verify_signature: False}``); here
verification is nominally ON but the allow-list whitelists the no-signature algorithm — a different
AST node (a literal list on the ``algorithms`` kwarg). content.jwt_signature_disabled's docstring explicitly declares this
variant out of its scope and names content.jwt_none_alg as the home for it.

Reuses ``substrate.factories.jwt_decode_callee_chain`` (the shared jwt/jose ``decode``-call gate, also used
by content.jwt_signature_disabled — extracted 2026-07-09 from what were two hand-duplicated copies) so a non-jwt ``decode``
whose ``algorithms`` list contains ``"none"`` — e.g. a compression layer where ``"none"`` means "no
compression" — stays silent, and ``substrate.factories.ast_introduced_predicate`` for the active-code AST
gate (a comment/string MENTION never fires). A legitimate case (a test decoding a
deliberately-unsigned token) is annotated ``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) a non-literal ``algorithms`` (``algorithms=algs`` / built dynamically) is
not a literal list at the call site -> not matched. (b) the ENCODE side (``jwt.encode(..., algorithm=
"none")``, signing an unsigned token) is a different shape, out of this verifier-path pattern's scope
(mirrors content.jwt_signature_disabled). (c) an aliased ``from jwt import decode; decode(t, algorithms=["none"])`` has no jwt
token in the callee chain -> not matched (FN-safe; an FP on an honest non-jwt ``decode`` is the binding harm).

Knight-Leveson: stdlib ast/re only.
"""
from __future__ import annotations
import ast
from typing import Optional

from makoto.substrate.factories import ast_introduced_predicate, jwt_decode_callee_chain

from makoto.core.lexicons import _PY_FILE_RX as _TARGET_RX


def _is_none_alg(node) -> bool:
    """True iff `node` is a string Constant whose value is the unsigned `none` algorithm (any case)."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower() == "none"


def _algorithms_whitelists_none(value) -> bool:
    """True iff the `algorithms=` value is a literal list/tuple/set containing a 'none' alg string."""
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return False
    return any(_is_none_alg(elt) for elt in value.elts)


def _jwt_none_node_match(node: ast.AST) -> Optional[str]:
    if jwt_decode_callee_chain(node) is None:
        return None
    for kw in node.keywords:
        if kw.arg == "algorithms" and _algorithms_whitelists_none(kw.value):
            return 'algorithms=["none"]'
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_jwt_none_node_match)


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Don't put 'none' in a jwt/jose `decode(..., algorithms=[...])` allow-list. The JWT 'none' algorithm means NO signature, so whitelisting it makes `decode` ACCEPT a forged/unsigned token while still 'succeeding' -- the signature check becomes an illusory pass (CWE-347; PyJWT CVE-2022-29217). List only real signing algorithms (e.g. `algorithms=['RS256']`). If you are deliberately decoding a known-unsigned token in a test, annotate the line `makoto-allow: <reason>`."
DESCRIPTION = "JWT decode allow-list whitelists the unsigned 'none' algorithm (alg-confusion bypass)"

CHECK = _Check(id='content.jwt_none_alg', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('jwt', 'jose', 'pyjwt', 'algorithms'), retry_hint=RETRY_HINT, description=DESCRIPTION)
