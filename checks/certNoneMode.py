"""pattern 1.29 predicate — certificate verification disabled via verify_mode = CERT_NONE
(active-code only).

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, an assignment that
turns off an SSLContext's certificate verification:
  * ``<ctx>.verify_mode = ssl.CERT_NONE``
  * ``<ctx>.verify_mode = CERT_NONE``        (CERT_NONE imported into scope)

Materiality: ``SSLContext.verify_mode = CERT_NONE`` makes the context accept ANY peer certificate —
the cert-identity integrity check becomes a no-op while the handshake still "succeeds". This is the
assignment 1.26 deliberately punts: a BARE ``ssl.CERT_NONE`` is also the right-hand side of a
legitimate COMPARISON (``if mode == ssl.CERT_NONE:``), so 1.26 does not match CERT_NONE at all. The
ASSIGNMENT context disambiguates — you do not ``==``-compare by assigning, and assigning CERT_NONE
to a ``verify_mode`` attribute is unambiguously disabling verification, never reading it.

Active-code only (lib.factories.parse_introduced): a comment / string / docstring mentioning the shape
never fires. A genuinely-legitimate case (a localhost test server with no CA) is annotated
``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) ``ctx.verify_mode = ssl.CERT_OPTIONAL`` is a WEAKER setting, not a full
disable, and is left out of this pattern's honest scope (CERT_NONE is the unambiguous off).
(b) routing CERT_NONE through an intermediate variable (``mode = ssl.CERT_NONE; ctx.verify_mode =
mode``) is not a literal CERT_NONE at the assignment site -> not matched. (c) a bare local
``verify_mode = ssl.CERT_NONE`` (Name target, not yet wired to a context attribute) is not matched.

Knight-Leveson: stdlib ast/re only.
"""
# jscpd note (2026-07-09): flagged as a clone against paramikoHostKeyWeakened.py / certReqsNone.py /
# jwtSignatureDisabled.py. Verified: the matched span is only this docstring's closing
# "Knight-Leveson" line + the standard `from __future__ import annotations` / `import ast` /
# `from typing import Optional` / `from makoto.substrate.factories import ast_introduced_predicate,
# <fn>` header every ast_introduced_predicate-style check module repeats by house style -- it ends
# before any function body, so no logic is duplicated. Python import statements and a repeated
# documentation-convention sentence are not extractable into a shared helper. The package's real
# duplicate-LOGIC gate is tests/test_no_alpha_duplicate_functions.py's AST alpha-equivalence scan,
# which this file does not trip.
from __future__ import annotations
import ast
from typing import Optional

from makoto.substrate.factories import ast_introduced_predicate, is_cert_none

from makoto.core.lexicons import _PY_FILE_RX as _TARGET_RX


def _cert_none_node_match(node: ast.AST) -> Optional[str]:
    # `<ctx>.verify_mode = CERT_NONE` — an ATTRIBUTE-target assignment (the material disable;
    # a bare Name target is a not-yet-applied local, an acknowledged FN).
    if not isinstance(node, ast.Assign) or not is_cert_none(node.value):
        return None
    for tgt in node.targets:
        if isinstance(tgt, ast.Attribute) and tgt.attr == "verify_mode":
            return "verify_mode = CERT_NONE"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_cert_none_node_match)


from makoto.substrate._loader import Check as _Check
RETRY_HINT = "Don't set an SSLContext's `verify_mode = ssl.CERT_NONE`. That makes the context accept ANY peer certificate -- the cert-identity check becomes a no-op while the handshake still 'succeeds'. Use CERT_REQUIRED with a proper trust store (or pin a CA); if a localhost test server with no CA is genuinely required, annotate the line `makoto-allow: <reason>`."
DESCRIPTION = 'certificate verification disabled (SSLContext verify_mode = CERT_NONE)'

CHECK = _Check(id='content.cert_none_mode', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('CERT_NONE',), retry_hint=RETRY_HINT, description=DESCRIPTION)
