"""pattern 1.26 sentinels — TLS / certificate verification disabled (active-code only).

1.26 fires when a PreToolUse Write/Edit INTRODUCES, as REAL Python code (not a
comment / string / docstring mention), a TLS-verification disable:
  * a call keyword `verify=False` or `check_hostname=False`,
  * an `ssl._create_unverified_context` attribute access,
  * an assignment `<x>.check_hostname = False`.

Materiality: disabling TLS certificate/hostname verification turns a real
integrity check (the peer is who it claims) into a no-op — a textbook integrity
weakening. The "only active code" AST gate (lib.factories.parse_introduced) is what
makes the fire MATERIAL: a regex would also block a comment that merely MENTIONS
`verify=False`, which is an illusory word. These adversarial near-misses pin the
discrimination (a green corpus alone does not prove low FP — these do).
"""
from __future__ import annotations
from makoto.checks.certVerifyDisabled import predicate
from makoto.schema import PreCheck

_PAT = PreCheck(id="content.cert_verify_disabled", fire_level="error",
               description="TLS/certificate verification disabled", retry_hint="x")


def _fires(file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === TRUE POSITIVES: real active code disabling TLS verification =================

def test_tp_requests_verify_false():
    assert _fires("client.py", "import requests\nr = requests.get(url, verify=False)\n")


def test_tp_httpx_verify_false():
    assert _fires("api.py", "client = httpx.Client(verify=False)\n")


def test_tp_unverified_context():
    assert _fires("net.py", "import ssl\nctx = ssl._create_unverified_context()\n")


def test_tp_check_hostname_keyword():
    assert _fires("net.py", "ctx = ssl.create_default_context(check_hostname=False)\n")


def test_tp_check_hostname_assigned():
    assert _fires("net.py", "ctx = ssl.create_default_context()\nctx.check_hostname = False\n")


def test_tp_edit_new_string_fragment():
    """An Edit that introduces the disable as an indented statement fragment still parses."""
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "client.py",
                          "new_string": "        resp = session.get(u, verify=False)\n"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === NEAR-MISS NEGATIVES: must STAY SILENT (the active-code gate's whole point) ==

def test_neg_verify_true():
    """verify=True is the SAFE setting -> silent."""
    assert not _fires("client.py", "r = requests.get(url, verify=True)\n")


def test_neg_comment_mention():
    """a COMMENT mentioning the disable is not active code -> silent (the key win)."""
    assert not _fires("client.py", "# never call requests.get(url, verify=False) in prod\n")


def test_neg_docstring_mention():
    assert not _fires("client.py", '"""Do not use requests.get(u, verify=False) here."""\n')


def test_neg_string_literal_mention():
    assert not _fires("client.py", 'BAD_EXAMPLE = "requests.get(u, verify=False)"\n')


def test_neg_makoto_allow_exempts():
    body = "r = requests.get(url, verify=False)  # makoto-allow: pinned internal self-signed dev host\n"
    assert not _fires("client.py", body)


def test_neg_non_python_target():
    """a .md doc containing the shape is prose, not config/code -> silent."""
    assert not _fires("README.md", "Example: requests.get(u, verify=False)\n")


def test_neg_jwt_decode_verify_false():
    """`verify=False` on a NON-TLS callee (PyJWT signature, not TLS) -> silent (callee gate).
    Reviewer-cited FP, 2026-06-02 phase-boundary review."""
    assert not _fires("auth.py", "data = jwt.decode(token, verify=False)\n")


def test_neg_non_tls_verify_kwargs():
    """custom APIs whose `verify`/`check_hostname` kwarg is unrelated to TLS -> silent."""
    for body in ("widget.render(data, verify=False)\n",
                 "form.clean(d, verify=False)\n",
                 "parser.parse(src, verify=False)\n",
                 "m = Model.model_validate(raw, verify=False)\n",
                 "thing.configure(check_hostname=False)\n"):
        assert not _fires("app.py", body), f"non-TLS verify-kwarg FP: {body!r}"


def test_neg_unrecognised_callee_get_kwarg():
    """a bare `.get(verify=False)` on a non-client object (db/cache) -> silent (no client token)."""
    assert not _fires("store.py", "row = db.get(key, verify=False)\n")


def test_tp_session_get_recognised():
    """a recognised client token in the callee chain still fires (TP preserved)."""
    assert _fires("client.py", "r = session.get(u, verify=False)\n")


def test_tp_chained_requests_session():
    """`requests.Session().get(verify=False)` — chain descends through the intermediate Call so the
    `requests` token is seen (else it would be a FN)."""
    assert _fires("client.py", "r = requests.Session().get(u, verify=False)\n")


def test_neg_cert_none_comparison_not_matched():
    """reading/comparing CERT_NONE is not disabling it; v1 does not match CERT_NONE -> silent."""
    assert not _fires("net.py", "if ctx.verify_mode == ssl.CERT_NONE:\n    warn()\n")


def test_neg_non_check_hostname_attribute_assigned():
    """`<x>.<other> = False` on an attribute OTHER than check_hostname -> silent.
    Pins the `and` in `isinstance(tgt, ast.Attribute) and tgt.attr == 'check_hostname'`:
    only an Attribute target NAMED check_hostname is a TLS disable. Flipping `and`->`or`
    would fire on ANY `<attr> = False` assignment (e.g. `ctx.verify_mode = False`)."""
    assert not _fires("net.py", "ctx.verify_mode = False\n")


def test_neg_unparseable_fragment_silent():
    """an unparseable Edit fragment is never confirmed active -> silent (FN-safe)."""
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "client.py", "new_string": ", verify=False)"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None


def test_neg_stop_event_ignored():
    evt = {"hook_event_name": "Stop", "last_assistant_message": "requests.get(u, verify=False)"}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None
