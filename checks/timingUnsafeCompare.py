"""pattern 1.30 predicate — timing-unsafe ==/!= comparison of a SECRET/HMAC/digest
(active-code only). The "compare-digest" shape.

Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, as REAL Python code, an ``==``/``!=``
Compare where ONE operand is UNAMBIGUOUSLY a cryptographic secret/digest value:
  * a ``.hexdigest()`` / ``.digest()`` method call (the value returned by hashing), or
  * a Name/Attribute carrying a STRONG crypto token
    (hmac/hexdigest/signature/csrf/otp/totp/hotp/passphrase/nonce).

Materiality: ``==``/``!=`` on a digest/HMAC is a byte-by-byte short-circuiting compare that leaks
match-length timing — a remote timing attack recovers the secret one byte at a time (CWE-208). The
check still "passes", but its constant-time property — the thing that makes it a SAFE verifier — is
silently absent. The fix is ``hmac.compare_digest(a, b)``, which removes the ``==``; applying it
makes this pattern go silent exactly when the developer remediates (teeth-correct).

PRECISION GATE (zero-FP). Only an UNAMBIGUOUSLY cryptographic operand anchors a fire — a
``.hexdigest()``/``.digest()`` call or one of the STRONG tokens above. The POLYSEMOUS credential
words (token / sig / secret / password / mac / tag / key) are DELIBERATELY EXCLUDED: a lexer
``token``, a network ``mac`` address, a parser ``tag``, a config ``key`` are ubiquitous honest
non-secret comparisons (``if start_tag == end_tag``, ``if src_mac == dst_mac``, ``if config_key ==
expected_key``), and no lexical gate separates the real-secret use from the mundane one — so firing
on them is an FP, the binding harm for a BLOCKING gate. Two further FP guards:
  * METADATA DEMOTE — a strong token qualified by a descriptor suffix (``signature_algorithm``,
    ``digest_size``) names metadata ABOUT the secret, not the value -> silent.
  * VALUE-ONLY — a strong word that is a Call's *function* (``inspect.signature(f) ==
    inspect.signature(g)``) is a function NAMED signature, not a secret value -> silent. Only a
    ``.hexdigest()``/``.digest()`` call (a hash METHOD that returns a digest) anchors via a Call.

A sentinel-constant operand (None / bool / 0 / "" / b"") voids the match — that is a presence/state
check (``if digest is None``, ``if otp == ""``), never a secret-vs-secret equality.

Active-code only (lib.factories.parse_introduced): a comment / string / docstring mentioning ``digest ==
x`` never fires. A legitimate non-constant-time compare (a test stub, a non-secret value that merely
shares a strong name) is annotated ``makoto-allow: <reason>`` and stays silent.

ACKNOWLEDGED FN (v1): (a) a secret behind a fully-generic or POLYSEMOUS name (``if a == b`` with
HMACs in a/b; ``if token == expected`` with a real token; ``password == stored``) has no STRONG
anchor -> silent — the deliberate price of killing the lexer-token / MAC-address / config-key / form-
password FP classes. (b) a digest assigned to a generic local first (``h = m.hexdigest(); h ==
provided``) is not in the Compare -> silent. (c) ``in``/``not in`` membership and ``<``/``>``
ordering are out of scope (the timing-unsafe shape is ==/!=).

Knight-Leveson: stdlib ast/re only.
"""
from __future__ import annotations
import ast
import re
from typing import Optional

from makoto.lib.factories import ast_introduced_predicate

from makoto.lexicons import _PY_FILE_RX as _TARGET_RX

# STRONG: unambiguously cryptographic identifier tokens; a SINGLE such operand makes the compare
# timing-sensitive. The polysemous credential words (token/sig/secret/password/mac/tag/key) are
# excluded by design — see the module docstring's PRECISION GATE.
_STRONG_RX = re.compile(
    r"(?i)(?:^|_)(hmac|hexdigest|signature|csrf|otp|totp|hotp|passphrase|nonce)(?:$|_)"
)
# descriptor suffixes mark metadata ABOUT the secret (size/len/name/algorithm/...), not the value.
_METADATA_SUFFIX_RX = re.compile(
    r"(?i)_(size|len|length|type|name|algorithm|algo|id|field|header|count|index|idx"
    r"|version|format|kind|class|mode|status|state|prefix|suffix|expiry|ttl|url|uri|path)$"
)
# the two hashlib/hmac methods that RETURN a digest value: a call to either is a digest operand.
_DIGEST_METHODS = frozenset({"hexdigest", "digest"})


def _is_sentinel_constant(node) -> bool:
    """None / bool / 0 / '' / b'' -> a presence/state check, not secret-vs-secret equality."""
    if not isinstance(node, ast.Constant):
        return False
    v = node.value
    return v is None or isinstance(v, bool) or v == 0 or v == "" or v == b""


def _is_strong_operand(node) -> bool:
    """True iff `node` is UNAMBIGUOUSLY a cryptographic secret/digest VALUE."""
    # a `.hexdigest()` / `.digest()` method call returns a hash value.
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in _DIGEST_METHODS):
        return True
    # a Name / Attribute VALUE carrying a strong token. NOT a Call's func (that is a function named
    # `signature`/etc — e.g. `inspect.signature(f)` — not a secret value), NOT metadata-suffixed.
    if isinstance(node, ast.Name):
        tok = node.id
    elif isinstance(node, ast.Attribute):
        tok = node.attr
    else:
        return False
    if _METADATA_SUFFIX_RX.search(tok):
        return False
    return _STRONG_RX.search(tok) is not None


def _cd_node_match(node: ast.AST) -> Optional[str]:
    if not isinstance(node, ast.Compare) or not node.ops:
        return None
    if not all(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
        return None
    operands = [node.left] + list(node.comparators)
    if any(_is_sentinel_constant(o) for o in operands):
        return None
    if any(_is_strong_operand(o) for o in operands):
        return "timing-unsafe == of a secret/digest (use hmac.compare_digest)"
    return None


predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_cd_node_match)


from makoto.checks._loader import Check as _Check
RETRY_HINT = "Don't compare a secret/HMAC/digest with `==`/`!=`. A byte-by-byte short-circuiting compare leaks match-length timing (CWE-208), letting a remote attacker recover the secret one byte at a time -- the check still 'passes' but its constant-time property, the thing that makes it a SAFE verifier, is gone. Use `hmac.compare_digest(a, b)`. If a value merely shares a crypto name but is not a live secret comparison (a test asserting a known-good digest), annotate the line `makoto-allow: <reason>`."
DESCRIPTION = 'timing-unsafe ==/!= comparison of a secret/HMAC/digest (use hmac.compare_digest)'

CHECK = _Check(id='content.timing_unsafe_compare', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('digest', 'hmac', 'signature', 'csrf', 'otp', 'passphrase', 'nonce'), retry_hint=RETRY_HINT, description=DESCRIPTION)
