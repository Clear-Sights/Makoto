"""pattern 1.29 sentinels — cert verification disabled via verify_mode = CERT_NONE (active-code only).

1.29 fires when a PreToolUse Write/Edit INTRODUCES, as REAL Python code, an assignment
`<ctx>.verify_mode = ssl.CERT_NONE` (or bare `CERT_NONE`). The ASSIGNMENT context is the
discriminator: a COMPARISON `if mode == ssl.CERT_NONE:` reads the constant (legitimate) and stays
silent, while an assignment to a `verify_mode` attribute unambiguously disables cert verification.
This is the shape 1.26 deliberately punts. The "only active code" AST gate makes the fire MATERIAL.
The near-misses below pin the discrimination — a green corpus alone does not prove low FP; these do.
"""
from __future__ import annotations
from makoto.checks.certNoneMode import predicate
from makoto.core.schema import PreCheck

_PAT = PreCheck(id="content.cert_none_mode", fire_level="error",
               description="cert verification disabled (verify_mode = CERT_NONE)", retry_hint="x")


def _fires(file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === TRUE POSITIVES: real active code disabling cert verification =================

def test_tp_ssl_cert_none_attr():
    assert _fires("net.py", "import ssl\nctx.verify_mode = ssl.CERT_NONE\n")


def test_tp_bare_cert_none_name():
    assert _fires("net.py", "from ssl import CERT_NONE\nctx.verify_mode = CERT_NONE\n")


def test_tp_self_attr_chain():
    assert _fires("net.py", "self.ssl_ctx.verify_mode = ssl.CERT_NONE\n")


def test_tp_edit_new_string_fragment():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "net.py",
                          "new_string": "        context.verify_mode = ssl.CERT_NONE\n"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === NEAR-MISS NEGATIVES: must STAY SILENT ========================================

def test_neg_cert_none_comparison():
    """reading/comparing CERT_NONE is not disabling it -> silent (the assignment discriminator)."""
    assert not _fires("net.py", "if ctx.verify_mode == ssl.CERT_NONE:\n    warn()\n")


def test_neg_cert_required_assignment():
    """assigning the SAFE setting (CERT_REQUIRED) -> silent."""
    assert not _fires("net.py", "ctx.verify_mode = ssl.CERT_REQUIRED\n")


def test_neg_cert_optional_out_of_scope():
    """CERT_OPTIONAL is weaker but not the unambiguous off; v1 leaves it out of scope -> silent."""
    assert not _fires("net.py", "ctx.verify_mode = ssl.CERT_OPTIONAL\n")


def test_neg_other_attr_assigned_cert_none():
    """CERT_NONE assigned to an attribute OTHER than verify_mode -> silent (pins the attr name)."""
    assert not _fires("net.py", "ctx.default_mode = ssl.CERT_NONE\n")


def test_neg_bare_local_name_target():
    """a bare local `verify_mode = ssl.CERT_NONE` (Name target, not wired to a context) is an
    acknowledged FN -> silent."""
    assert not _fires("net.py", "verify_mode = ssl.CERT_NONE\n")


def test_neg_comment_mention():
    assert not _fires("net.py", "# do not set ctx.verify_mode = ssl.CERT_NONE in prod\n")


def test_neg_docstring_mention():
    assert not _fires("net.py", '"""Avoid ctx.verify_mode = ssl.CERT_NONE here."""\n')


def test_neg_string_literal_mention():
    assert not _fires("net.py", 'BAD = "ctx.verify_mode = ssl.CERT_NONE"\n')


def test_neg_makoto_allow_exempts():
    body = ("ctx.verify_mode = ssl.CERT_NONE  "
            "# makoto-allow: localhost test server, no CA available\n")
    assert not _fires("net.py", body)


def test_neg_non_python_target():
    assert not _fires("README.md", "Set ctx.verify_mode = ssl.CERT_NONE to skip verification\n")


def test_neg_unparseable_fragment_silent():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "net.py", "new_string": "verify_mode = ssl."}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None


def test_neg_stop_event_ignored():
    evt = {"hook_event_name": "Stop",
           "last_assistant_message": "ctx.verify_mode = ssl.CERT_NONE"}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None
