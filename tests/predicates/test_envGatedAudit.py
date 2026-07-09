"""pattern 1.2 sentinels — env-gated audit / verification code (active-code only).

1.2 fires when a PreToolUse Write/Edit INTRODUCES, as REAL Python code (not a comment /
string / docstring mention), an `if <env-read>:` whose guarded body — OR the env-var key
itself — NAMES an integrity / audit / verification concept (lexicons._INTEG_VOCAB:
audit|verif|integrit|attest|checksum|signatur|tamper|provenance). Env-read =
os.environ.get(...) / os.getenv(...) / os.environ[...] / the bare imported getenv(...) form.

Materiality: gating an audit trail / verification check behind an env var means the check
runs only when someone opts in — a silently-disable-able integrity check (a HOLLOWED word:
the audit survives in name while its guarantee is gutted). This is makoto's own CLAUDE.md
convention ("Audit/verification code gated behind an env var").

Why these near-misses (cert 2026-06-02, warning-tier-elimination:43, which CUT the old
content-string matcher): the prior regex (1) fired on MENTIONS in comments/strings/docs
(instance-vs-mention FP — it even targeted .md, firing on CLAUDE.md describing the shape);
(2) required a literal `AUDIT` in the var NAME, a flat FN on a BODY-only signal like
`if os.environ.get("MAKOTO_SHADOW"): run_integrity_check()`; (3) matched only
`os.environ.get(` — `os.getenv()` was a flat FN. The TPs below pin (2)+(3) are now caught;
the near-misses pin (1) is dissolved by the active-code AST gate AND a bare feature flag
(no integrity token) stays silent (a green corpus alone does not prove low FP — these do).
"""
from __future__ import annotations
from makoto.checks.envGatedAudit import predicate
from makoto.core.schema import PreCheck

_PAT = PreCheck(id="content.env_gated_audit", fire_level="error",
               description="env-gated audit/verification code", retry_hint="x")


def _fires(file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === TRUE POSITIVES: real active code env-gating an integrity/audit/verification op ==========

def test_tp_claude_md_example_key_names_audit():
    """The CLAUDE.md convention example: env-var KEY names the audit -> fire."""
    assert _fires("app.py", "if os.environ.get('ENABLE_AUDIT_TRAIL'):\n    write_audit_trail()\n")


def test_tp_body_only_signal_getenv_the_old_FN():
    """The cert's documented FN: KEY has NO literal AUDIT, the BODY runs the integrity op,
    and the form is os.getenv() (not os.environ.get). The old body_rx missed all three."""
    assert _fires("core.py", "if os.getenv('MAKOTO_SHADOW'):\n    run_integrity_check()\n")


def test_tp_environ_subscript_key_names_verify():
    """os.environ[...] subscript form; key names verification -> fire."""
    assert _fires("net.py", "if os.environ['VERIFY_PEER_MODE']:\n    enable_strict()\n")


def test_tp_bare_imported_getenv():
    """`from os import getenv` then a bare getenv(...) gate; key names audit -> fire."""
    assert _fires("svc.py", "from os import getenv\nif getenv('AUDIT_LOG'):\n    log_it()\n")


def test_tp_generic_env_name_body_verifies():
    """A non-integrity env NAME but the gated body calls verify/attest code -> fire (name-agnostic)."""
    assert _fires("sign.py", "if os.getenv('DEBUG_X'):\n    attest_signatures(payload)\n")


def test_tp_edit_new_string_indented_fragment():
    """An Edit that introduces the gate as an INDENTED statement fragment still parses+fires."""
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "app.py",
                          "new_string": "        if os.getenv('AUDIT_MODE'):\n            do_audit()\n"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === NEAR-MISS NEGATIVES: must STAY SILENT (the discrimination the corpus alone can't prove) ==

def test_neg_comment_mention():
    """A COMMENT mentioning the shape is not active code -> silent (the key mention-vs-instance win)."""
    assert not _fires("app.py", "# if os.environ.get('AUDIT'): write_audit_trail()  -- don't do this\n")


def test_neg_docstring_mention():
    assert not _fires("app.py", '"""StopCheck with AUDIT: if os.getenv(\'AUDIT\'): run_audit()."""\n')


def test_neg_string_literal_mention():
    assert not _fires("app.py", "EXAMPLE = \"if os.getenv('AUDIT'): run_audit()\"\n")


def test_neg_makoto_allow_exempts():
    body = ("if os.environ.get('ENABLE_AUDIT_TRAIL'):  # makoto-allow: app feature, user-facing audit log\n"
            "    write_audit_trail()\n")
    assert not _fires("app.py", body)


def test_neg_plain_feature_flag_no_integrity_token():
    """A bare feature flag — no integrity token in the env KEY or the body -> silent. THE discrimination."""
    assert not _fires("ui.py", "if os.getenv('DARK_MODE'):\n    render_dark()\n")


def test_neg_perf_toggle_no_integrity_token():
    assert not _fires("cache.py", "if os.environ.get('ENABLE_CACHE'):\n    setup_cache(size=64)\n")


def test_neg_env_read_not_gating_an_if():
    """An env read in an ASSIGNMENT (not an `if` test) is config, not a gated check -> silent.
    Mirrors makoto's own reads (install.py / state.py / _dispatch.py) — none must fire."""
    assert not _fires("state.py", "audit_dir = os.environ.get('AUDIT_DIR', '/tmp')\n")


def test_neg_makoto_disable_read_is_not_an_audit_gate():
    """makoto's own `if os.environ.get('MAKOTO_DISABLE_GATES'): ...` — the KEY names no integrity
    concept and the body names none -> silent (this is pattern 1.23's bypass domain, not 1.2's)."""
    assert not _fires("_dispatch.py", "if os.environ.get('MAKOTO_DISABLE_GATES'):\n    return None\n")


def test_neg_string_comparison_value_does_not_self_trigger():
    """`== "audit"` is a COMPARISON VALUE (a str Constant), not a code identifier -> silent.
    Pins that the body-token check reads active identifiers (Name/Attribute), never string literals."""
    assert not _fires("cfg.py", "if os.getenv('RUN_MODE') == 'audit':\n    configure()\n")


def test_neg_non_env_gate_with_audit_body():
    """An audit op gated on a NON-env condition (user.is_admin) -> silent. 1.2 requires an ENV read;
    a non-env gate is an ordinary conditional, not an opt-in-disable of the check."""
    assert not _fires("app.py", "if user.is_admin:\n    write_audit_trail()\n")


def test_neg_non_python_target_md():
    """A .md doc containing the shape is prose, not code -> silent (target is .py only; .md was the
    old detector's worst FP, firing on CLAUDE.md itself)."""
    assert not _fires("README.md", "Example: if os.getenv('AUDIT'): write_audit_trail()\n")
