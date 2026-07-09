"""pattern 1.26 predicate — TLS / certificate verification DISABLED (active-code only).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, a
disable of TLS peer/hostname verification:
  * a call keyword ``verify=False``      (requests / httpx / session.get(..., verify=False))
  * a call keyword ``check_hostname=False``
  * an assignment ``<x>.check_hostname = False``
  * an ``ssl._create_unverified_context`` attribute access (the stdlib's explicitly-
    named "unverified" SSL context).

Materiality: TLS certificate/hostname verification IS the integrity check that the
peer is who it claims to be. Setting ``verify=False`` / using an unverified context
turns that check into a no-op while the call still "succeeds" — a real verifier
silently weakened. Caught regardless of file (the shape is intrinsically a weakening,
like a security linter rule), but ONLY on active code: the ``parse_introduced`` AST
gate means a comment, string literal, or docstring that merely MENTIONS ``verify=False``
never fires (an illusory word). A genuinely-legitimate case (e.g. a pinned internal
self-signed dev host) is annotated with ``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) ``ctx.verify_mode = ssl.CERT_NONE`` is NOT matched — a bare
``ssl.CERT_NONE`` attribute is also used in legitimate *comparisons* (``mode == CERT_NONE``),
so matching it without assignment context would risk an FP. (b) a ``verify=False`` on a
requests/httpx call made through an UNRECOGNISED variable name (``s.get(u, verify=False)``
where ``s`` is a ``Session`` bound earlier) is NOT matched — the callee gate (below) needs a
known HTTP/TLS token in the callee chain. Both are FN-safe residuals: for a BLOCKING gate an
FP (false-blocking honest ``jwt.decode(verify=False)`` etc.) is the binding harm, so the
keyword match is scoped to a recognised client callee even at the cost of these FNs.

Knight-Leveson: stdlib ast/re only.
"""
from __future__ import annotations
import ast
import re
from typing import Optional

from makoto.substrate.factories import ast_introduced_predicate, callee_chain, is_false_const

from makoto.core.lexicons import _PY_FILE_RX as _TARGET_RX
# call-keyword names whose ``=False`` value disables a TLS check.
_FALSE_KEYWORDS = frozenset({"verify", "check_hostname"})
# attribute names that are themselves a TLS-verification disable.
_UNVERIFIED_ATTRS = frozenset({"_create_unverified_context"})
# CALLEE GATE (phase-boundary review fix, 2026-06-02): the bare keyword `verify=False`
# is NOT TLS-specific — honest non-TLS APIs use a `verify` kwarg too (`jwt.decode(verify=False)`,
# `form.clean(verify=False)`, `widget.render(verify=False)`, pydantic `model_validate(verify=False)`).
# So the keyword only fires when the call's CALLEE chain names a known HTTP/TLS client/context —
# the same precision bandit's B501 uses. Strong library/object tokens only (no bare `.get`/`.post`,
# which would re-introduce `cache.get(verify=False)` FPs). The unverified-context attribute and the
# `ctx.check_hostname = False` assignment stay unconditional (both intrinsically TLS).
_TLS_CALLEE_RX = re.compile(
    r"(?i)(requests|httpx|aiohttp|urllib3|pycurl|\bsession\b|http[_.]?client"
    r"|ssl|sslcontext|create_default_context|create_urllib3_context|wrap_socket)"
)


def _tls_node_match(node: ast.AST) -> Optional[str]:
    # `ssl._create_unverified_context` attribute access (the stdlib's explicitly-"unverified" ctx)
    if isinstance(node, ast.Attribute) and node.attr in _UNVERIFIED_ATTRS:
        return f".{node.attr}"
    # `<x>.check_hostname = False` attribute assignment (check_hostname is the SSLContext attribute)
    if isinstance(node, ast.Assign) and is_false_const(node.value):
        for tgt in node.targets:
            if isinstance(tgt, ast.Attribute) and tgt.attr == "check_hostname":
                return "check_hostname=False (assigned)"
    # `verify=False` / `check_hostname=False` keyword — ONLY on an HTTP/TLS-client call
    if isinstance(node, ast.Call) and _TLS_CALLEE_RX.search(callee_chain(node)):
        for kw in node.keywords:
            if kw.arg in _FALSE_KEYWORDS and is_false_const(kw.value):
                return f"{kw.arg}=False"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_tls_node_match)


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Don't disable TLS verification. Setting verify=False / check_hostname=False / using ssl._create_unverified_context() turns the peer-identity check into a no-op while the call still 'succeeds' -- a silently weakened verifier. Use proper certs (or pin a CA); if a self-signed internal host is genuinely required, annotate the line with `makoto-allow: <reason>`."
DESCRIPTION = 'TLS/certificate verification disabled (verify=False / unverified SSL context)'

CHECK = _Check(id='content.cert_verify_disabled', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('verify=False', 'check_hostname=False', '_create_unverified_context'), retry_hint=RETRY_HINT, description=DESCRIPTION)
