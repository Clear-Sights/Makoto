"""pattern 1.30 sentinels — timing-unsafe ==/!= of a secret/HMAC/digest (active-code only).

1.30 fires when a PreToolUse Write/Edit INTRODUCES, as REAL Python code, an ``==``/``!=`` Compare
with an UNAMBIGUOUSLY cryptographic operand — a ``.hexdigest()``/``.digest()`` call or a STRONG
token (hmac/hexdigest/signature/csrf/otp/totp/hotp/passphrase/nonce). The fix is
``hmac.compare_digest``, which removes the ``==`` (teeth-correct: remediation silences it).

The negatives below are the cited honest-FP classes the two-rule search surfaced — polysemous
`mac`/`tag`/`token`/`key` comparisons (network/parser/lexer/config), the function-`signature`
introspection compare, and the metadata-suffix cases. A green corpus alone does not prove low FP;
these adversarial near-misses pin the STRONG-only precision gate that keeps it zero-FP.
"""
from __future__ import annotations
from makoto.checks.timingUnsafeCompare import predicate
from makoto.core.schema import PreCheck

_PAT = PreCheck(id="content.timing_unsafe_compare", fire_level="error",
               description="timing-unsafe == of a secret/digest", retry_hint="x")


def _fires(file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === TRUE POSITIVES: real timing-unsafe secret/digest comparisons =================

def test_tp_hexdigest_call_vs_sig():
    assert _fires("auth.py", "if hmac.new(key, body).hexdigest() == sig:\n    ok()\n")


def test_tp_digest_call_both_sides():
    assert _fires("auth.py", "if a.digest() == b.digest():\n    ok()\n")


def test_tp_signature_names_neq():
    """webhook signature verification by `!=` on two signature values."""
    assert _fires("hook.py", "if computed_signature != provided_signature:\n    abort()\n")


def test_tp_csrf_token_eq():
    assert _fires("web.py", "if csrf_token == request.headers['X-CSRF']:\n    ok()\n")


def test_tp_otp_eq():
    assert _fires("auth.py", "if otp == user_otp:\n    grant()\n")


def test_tp_hotp_segment_token():
    assert _fires("auth.py", "if hotp_value == submitted_hotp:\n    grant()\n")


def test_tp_passphrase_neq():
    assert _fires("vault.py", "if passphrase != stored_passphrase:\n    deny()\n")


def test_tp_nonce_eq():
    assert _fires("crypto.py", "if nonce == request_nonce:\n    ok()\n")


def test_tp_edit_new_string_fragment():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "auth.py",
                          "new_string": "        if mac.hexdigest() == expected:\n            ok()\n"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === NEAR-MISS NEGATIVES: must STAY SILENT (the cited honest-FP classes) ===========

def test_neg_html_tag_compare():
    """parser tag equality — `tag` is polysemous, excluded by design."""
    assert not _fires("parser.py", "if start_tag == end_tag:\n    close()\n")


def test_neg_network_mac_compare():
    """MAC ADDRESS equality — `mac` is polysemous, not the HMAC sense."""
    assert not _fires("net.py", "if src_mac == dst_mac:\n    loop()\n")


def test_neg_config_key_compare():
    assert not _fires("conf.py", "if config_key == expected_key:\n    use()\n")


def test_neg_db_key_compare():
    assert not _fires("db.py", "if primary_key == foreign_key:\n    join()\n")


def test_neg_lexer_token_compare():
    assert not _fires("lexer.py", "if cur_token == prev_token:\n    merge()\n")


def test_neg_bare_token_vs_expected():
    """`token == expected` — the deliberate ACKNOWLEDGED FN: irreducibly polysemous, excluded so
    the lexer-token FP class cannot fire. FN-safe (an FP here is the binding harm)."""
    assert not _fires("auth.py", "if token == expected:\n    grant()\n")


def test_neg_function_signature_introspection():
    """`inspect.signature(...)` is a function NAMED signature (a Call func), not a secret value."""
    assert not _fires("typecheck.py",
                      "if inspect.signature(f) == inspect.signature(g):\n    ok()\n")


def test_neg_signature_algorithm_metadata():
    """metadata-suffix demote: `signature_algorithm` is metadata ABOUT a signature, not the value."""
    assert not _fires("jwt.py", "if signature_algorithm == 'RS256':\n    ok()\n")


def test_neg_digest_size_metadata():
    assert not _fires("hash.py", "if digest_size == 32:\n    ok()\n")


def test_neg_bare_digest_word_is_not_strong():
    """bare `digest` (newsletter/changelog digest) is NOT a strong token — only `hexdigest` and a
    `.digest()`/`.hexdigest()` CALL are. `if digest == 'daily':` is an honest frequency compare."""
    assert not _fires("mail.py", "if digest == 'daily':\n    send()\n")


def test_neg_password_form_compare():
    """form-field password equality — `password` is polysemous (plaintext form vs stored secret)."""
    assert not _fires("signup.py", "if new_password == confirm_password:\n    ok()\n")


def test_neg_sentinel_constant_none():
    assert not _fires("auth.py", "if otp is None:\n    reissue()\n")


def test_neg_sentinel_constant_empty_string():
    assert not _fires("auth.py", "if signature == '':\n    reject()\n")


def test_neg_sentinel_eq_none_literal():
    """`signature == None` is a presence check (not `is None`, but the same intent) -> voided by the
    `v is None` sentinel clause. Pins that clause: mutating `is None`->`is not None` would make a
    strong-operand-vs-None compare FIRE."""
    assert not _fires("auth.py", "if signature == None:\n    reject()\n")


def test_neg_sentinel_eq_zero_literal():
    """`otp == 0` is a zero/state check -> voided by the `v == 0` sentinel clause. Pins it:
    mutating `== 0`->`!= 0` would make a strong-operand-vs-0 compare FIRE."""
    assert not _fires("auth.py", "if otp == 0:\n    reissue()\n")


def test_neg_sentinel_eq_empty_bytes_literal():
    """`signature == b''` is an empty-bytes/presence check -> voided by the `v == b''` sentinel
    clause. Pins it: mutating `== b''`->`!= b''` would make a strong-operand-vs-empty-bytes FIRE."""
    assert not _fires("auth.py", "if signature == b'':\n    reject()\n")


def test_neg_ordering_not_equality():
    """`<`/`>` ordering is out of scope — only ==/!= leak the match-length timing."""
    assert not _fires("crypto.py", "if nonce < other_nonce:\n    skip()\n")


def test_neg_membership_not_equality():
    assert not _fires("auth.py", "if otp in valid_otps:\n    grant()\n")


def test_neg_comment_mention():
    assert not _fires("auth.py", "# if signature == sig: timing-unsafe, do not do this\n")


def test_neg_docstring_mention():
    assert not _fires("auth.py", '"""Avoid `if hmac == sig:` — use compare_digest."""\n')


def test_neg_string_literal_mention():
    assert not _fires("auth.py", 'BAD = "if signature == sig"\n')


def test_neg_makoto_allow_exempts():
    body = ("if signature == expected_signature:  "
            "# makoto-allow: test fixture asserting a known-good signature, not a live verifier\n    ok()\n")
    assert not _fires("test_sig.py", body)


def test_neg_non_python_target():
    assert not _fires("README.md", "if signature == sig: ...\n")


def test_neg_unparseable_fragment_silent():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "auth.py", "new_string": "== sig:\n"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None


def test_neg_stop_event_ignored():
    evt = {"hook_event_name": "Stop", "last_assistant_message": "if signature == sig:"}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None
