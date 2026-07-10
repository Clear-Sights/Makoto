"""content.cert_reqs_none predicate — certificate verification disabled via a cert_reqs=CERT_NONE kwarg.

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, a call that passes
``cert_reqs=CERT_NONE`` — turning off peer-certificate verification at the call site:
  * ``ssl.wrap_socket(sock, cert_reqs=ssl.CERT_NONE)``
  * ``context.wrap_socket(sock, cert_reqs=CERT_NONE)``
  * ``urllib3.PoolManager(cert_reqs=ssl.CERT_NONE)``

Materiality: ``cert_reqs=CERT_NONE`` instructs the TLS layer to require NO certificate from the peer —
the handshake "succeeds" against any (or no) certificate, so the cert-identity integrity check is a
no-op. This is the KWARG form, structurally DISTINCT from content.cert_none_mode: content.cert_none_mode matches the assignment
``<ctx>.verify_mode = CERT_NONE`` (an ``ast.Assign`` to a ``verify_mode`` attribute); this matches a
``cert_reqs=`` keyword on an ``ast.Call``. Different node type -> the same introduced text never
double-fires, and each form is caught in its own right.

Reuses ``substrate.factories.is_cert_none`` (the shared ``ssl.CERT_NONE`` / bare ``CERT_NONE`` recognizer, also
used by content.cert_none_mode) and ``substrate.factories.ast_introduced_predicate`` for the active-code AST gate. A comment /
docstring mention never fires; a genuinely-legitimate case (a localhost test client with no CA) is
annotated ``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) the urllib3 STRING form ``cert_reqs="CERT_NONE"`` is a string Constant, not
the ``ssl.CERT_NONE`` symbol, and is left out of this v1's honest scope (matching arbitrary
``"CERT_NONE"`` strings widens the FP surface; the symbol form is the unambiguous one). (b) routing
``CERT_NONE`` through a variable (``r = ssl.CERT_NONE; ...(cert_reqs=r)``) is not a literal at the call
site -> not matched. (c) ``cert_reqs=ssl.CERT_OPTIONAL`` is a weaker-but-not-off setting, out of scope
(CERT_NONE is the unambiguous disable, mirroring content.cert_none_mode's scope boundary).

Knight-Leveson: stdlib ast/re only.
"""
# jscpd note (2026-07-09): flagged as a clone against certNoneMode.py. Verified: the matched span
# is only this docstring's closing "Knight-Leveson" line + the standard house-style import header
# (`from __future__ import annotations` / `import ast` / `from typing import Optional` /
# `from makoto.substrate.factories import ast_introduced_predicate, is_cert_none`) -- both content.cert_none_mode and
# content.cert_reqs_none already share `is_cert_none` itself (the real logic is single-sourced in substrate/factories.py);
# what jscpd matches is just the import line naming that shared symbol, which ends before any
# function body. See tests/test_no_alpha_duplicate_functions.py for the package's real
# duplicate-logic gate.
from __future__ import annotations
import ast
from typing import Optional

from makoto.substrate.factories import ast_introduced_predicate, is_cert_none

from makoto.core.lexicons import _PY_FILE_RX as _TARGET_RX


def _cert_reqs_node_match(node: ast.AST) -> Optional[str]:
    if not isinstance(node, ast.Call):
        return None
    for kw in node.keywords:
        if kw.arg == "cert_reqs" and is_cert_none(kw.value):
            return "cert_reqs=CERT_NONE"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_cert_reqs_node_match)


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Don't pass `cert_reqs=ssl.CERT_NONE` to a TLS call (ssl.wrap_socket / SSLContext.wrap_socket / urllib3.PoolManager). It tells the TLS layer to require NO certificate from the peer, so the handshake 'succeeds' against any or no cert -- the cert-identity check becomes an illusory pass (CWE-295). Use `cert_reqs=ssl.CERT_REQUIRED` with a CA. For a localhost test client with no CA, annotate the line `makoto-allow: <reason>`."
DESCRIPTION = 'cert_reqs=ssl.CERT_NONE kwarg disables peer-certificate verification at the call site'

CHECK = _Check(id='content.cert_reqs_none', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('cert_reqs', 'CERT_NONE'), retry_hint=RETRY_HINT, description=DESCRIPTION)
