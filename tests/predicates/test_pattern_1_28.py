"""pattern 1.28 sentinels — JWT signature verification disabled (active-code only).

1.28 fires when a PreToolUse Write/Edit INTRODUCES, as REAL Python code, a disable of JWT
signature verification on a jwt/jose `decode` call: `verify=False` or
`options={"verify_signature": False}`. The callee gate (a jwt/jose token in the call chain)
is what keeps it zero-FP — an unrelated `verify=False` kwarg (TLS, forms, parsers) stays silent.
The "only active code" AST gate (lib.factories.parse_introduced) makes the fire MATERIAL: a comment /
string / docstring mentioning the shape never fires. These adversarial near-misses pin the
discrimination — a green corpus alone does not prove low FP; these do.
"""
from __future__ import annotations
from makoto.prechecks.precheck_1_28 import predicate
from makoto.schema import PreCheck

_PAT = PreCheck(id="1.28", fire_level="error",
               description="JWT signature verification disabled", retry_hint="x")


def _fires(file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === TRUE POSITIVES: real active code disabling JWT signature verification ========

def test_tp_jwt_decode_verify_false():
    assert _fires("auth.py", "import jwt\ndata = jwt.decode(token, key, verify=False)\n")


def test_tp_jwt_decode_options_verify_signature_false():
    assert _fires("auth.py",
                  'data = jwt.decode(token, options={"verify_signature": False})\n')


def test_tp_jose_jwt_decode_verify_false():
    assert _fires("auth.py", "claims = jose.jwt.decode(tok, key, verify=False)\n")


def test_tp_pyjwt_namespace_decode():
    assert _fires("auth.py", "d = pyjwt.decode(tok, verify=False)\n")


def test_tp_chained_jwt_instance_decode():
    """`JWT().decode(...)` through a jwt-namespaced constructor still carries the token."""
    assert _fires("auth.py", "d = jwt.JWT().decode(tok, verify=False)\n")


def test_tp_edit_new_string_fragment():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "auth.py",
                          "new_string": "        claims = jwt.decode(t, verify=False)\n"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === NEAR-MISS NEGATIVES: must STAY SILENT ========================================

def test_neg_verify_true():
    assert not _fires("auth.py", "data = jwt.decode(token, key, verify=True)\n")


def test_neg_options_verify_signature_true():
    assert not _fires("auth.py",
                      'data = jwt.decode(token, options={"verify_signature": True})\n')


def test_neg_options_without_verify_signature():
    assert not _fires("auth.py",
                      'data = jwt.decode(token, options={"require": ["exp"]})\n')


def test_neg_options_non_literal_dict():
    """`options=<var>` (a non-literal Dict) cannot be statically read as disabling the signature
    -> silent. Pins the `if not isinstance(value, ast.Dict): return False` guard: flipping that
    constant to True would fire on ANY `options=` argument (an acknowledged FN, never an FP)."""
    assert not _fires("auth.py", "data = jwt.decode(token, options=opts)\n")


def test_neg_comment_mention():
    assert not _fires("auth.py", "# never call jwt.decode(token, verify=False) in prod\n")


def test_neg_docstring_mention():
    assert not _fires("auth.py", '"""Do not use jwt.decode(t, verify=False) here."""\n')


def test_neg_string_literal_mention():
    assert not _fires("auth.py", 'BAD = "jwt.decode(t, verify=False)"\n')


def test_neg_makoto_allow_exempts():
    body = ("data = jwt.decode(token, verify=False)  "
            "# makoto-allow: test fixture decoding an intentionally-unsigned token\n")
    assert not _fires("auth.py", body)


def test_neg_non_python_target():
    assert not _fires("README.md", "Example: jwt.decode(t, verify=False)\n")


def test_neg_non_jwt_verify_false_callee():
    """`verify=False` on a NON-jwt callee stays silent (the callee gate) — this is what keeps
    1.28 from poaching 1.26's TLS shape or FP'ing on unrelated `verify` kwargs."""
    for body in ("r = requests.get(url, verify=False)\n",       # TLS -> 1.26's domain, not 1.28
                 "form.clean(d, verify=False)\n",
                 "parser.parse(src, verify=False)\n",
                 "row = db.get(key, verify=False)\n"):
        assert not _fires("app.py", body), f"non-jwt verify-kwarg FP: {body!r}"


def test_neg_jwt_encode_not_matched():
    """`encode` is the signing path, not the verifying path -> out of scope -> silent."""
    assert not _fires("auth.py", "tok = jwt.encode(claims, key, verify=False)\n")


def test_neg_aliased_decode_is_fn_safe():
    """`from jwt import decode; decode(t, verify=False)` has no jwt token in the callee chain ->
    not matched (acknowledged FN; FN-safe, never an FP)."""
    assert not _fires("auth.py", "decode(token, verify=False)\n")


def test_neg_similarly_named_callee_not_matched():
    """a callee whose name merely CONTAINS 'jwt' as a substring (not boundary-delimited) is not a
    jwt library token -> silent (no `myjwthelper.decode` FP)."""
    assert not _fires("app.py", "d = myjwthelper.decode(t, verify=False)\n")


def test_neg_unparseable_fragment_silent():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "auth.py", "new_string": ", verify=False)"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None


def test_neg_stop_event_ignored():
    evt = {"hook_event_name": "Stop", "last_assistant_message": "jwt.decode(t, verify=False)"}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None
