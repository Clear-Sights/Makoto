"""pattern 1.27 sentinels — verifier HOLLOWED (body gutted to return-True / pass).

1.27 fires when a PreToolUse Write/Edit INTRODUCES, on the constitution integrity-check
surface (`constitution/integrity/checks/*.py` — the exact path 1.1 anchors on), a
verifier-named FunctionDef whose ENTIRE body (after a docstring) is `return <truthy>` or
`pass`. That is the body-gutting cheat: the check still exists and "passes", but does no
checking. It is the deletion/short-circuit cousin of 1.1 (comparator-loosening) — the
refuter confirmed 1.1 does NOT cover it (1.1 needs startswith/in[]/re.match, none present
in `return True`). Active-code AST gate (lib.factories.parse_introduced): a docstring/comment
that MENTIONS the shape never fires. The narrow path anchor is what kills the FP on
permissive base-class/null-object `return True` methods (they live elsewhere).
"""
from __future__ import annotations
from makoto.checks.verifierBodyHollowed import predicate
from makoto.core.schema import PreCheck

_PAT = PreCheck(id="content.verifier_body_hollowed", fire_level="error",
               description="verifier hollowed — body gutted to return-True/pass", retry_hint="x")
_P = "/repo/constitution/integrity/checks/seal.py"


def _fires(file_path: str, content: str) -> bool:
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": file_path, "content": content}}
    return predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === TRUE POSITIVES: a hollowed verifier on the integrity-check surface ==========

def test_tp_return_true_only():
    assert _fires(_P, "def verify_seal(state):\n    return True\n")


def test_tp_pass_after_docstring():
    assert _fires(_P, 'def check_integrity(s):\n    """validate the seal."""\n    pass\n')


def test_tp_validate_returns_truthy_constant():
    assert _fires(_P, "def validate_chain(s):\n    return 1\n")


def test_tp_edit_new_string():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": _P, "new_string": "def assert_attested(s):\n    return True\n"}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is not None


# === NEAR-MISS NEGATIVES: must STAY SILENT ======================================

def test_neg_real_body_then_return_true():
    """a verifier that does real work before returning True is NOT hollow -> silent."""
    body = ("def verify_seal(state):\n"
            "    expected = compute(state)\n"
            "    if state.sig != expected:\n"
            "        return False\n"
            "    return True\n")
    assert not _fires(_P, body)


def test_neg_non_verifier_name_pass():
    """a non-verifier helper/dunder with `pass` is not a hollowed check -> silent."""
    assert not _fires(_P, "def __init__(self):\n    pass\n")


def test_neg_off_surface_permissive_default():
    """a permissive base-class `return True` OFF the integrity-check path -> silent (path gate)."""
    assert not _fires("/repo/app/policy.py", "def validate(self, v):\n    return True\n")


def test_neg_comment_mention():
    assert not _fires(_P, "# a hollowed check would be: def verify(): return True\n")


def test_neg_docstring_mention():
    assert not _fires(_P, '"""bad: def verify_seal(s): return True (hollowed)."""\n')


def test_neg_makoto_allow_exempts():
    body = "def verify_seal(state):\n    return True  # makoto-allow: trivially-true base, overridden in subclass\n"
    assert not _fires(_P, body)


def test_neg_return_false_not_hollow():
    """`return False` is not an always-pass hollow -> silent."""
    assert not _fires(_P, "def verify_seal(s):\n    return False\n")


def test_neg_unparseable_fragment_silent():
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": _P, "new_string": "def verify("}}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None


def test_neg_stop_event_ignored():
    evt = {"hook_event_name": "Stop", "last_assistant_message": "def verify_seal(s): return True"}
    assert predicate(current_event=evt, history=[], pattern=_PAT) is None


# === harvest Phase 1 — broadened arms (assert-True + swallowed-exception) ========
# TRUE POSITIVES (additive to the original hollow-body arm):

def test_tp_assert_true_verifier():
    """family C-core: a verifier whose only check is a tautological `assert True` -> fires."""
    assert _fires(_P, "def validate_policy(p):\n    assert True\n")


def test_tp_broad_except_returns_truthy():
    """family F: a broad `except Exception` that swallows the failure into `return True` -> fires."""
    assert _fires(_P, "def verify_chain(s):\n    try:\n        return _check(s)\n    except Exception:\n        return True\n")


def test_tp_bare_except_pass():
    """family F: a bare `except:` whose body is `pass` swallows the failure -> fires."""
    assert _fires(_P, "def check_seal(s):\n    try:\n        _verify(s)\n    except:\n        pass\n")


def test_tp_baseexception_tuple_swallow():
    """a tuple catching BaseException is still broad -> fires."""
    assert _fires(_P, "def verify_x(s):\n    try:\n        _v(s)\n    except (ValueError, BaseException):\n        return True\n")


# NEAR-MISS NEGATIVES (the broad-only + specific-type firewall, must STAY SILENT):

def test_neg_specific_except_degrade_open():
    """a SPECIFIC-typed except around an expected-unavailable dep is honest narrowing -> silent."""
    body = "def check_hsm(s):\n    try:\n        return _hsm.verify(s)\n    except HSMUnavailable:\n        return True\n"
    assert not _fires(_P, body)


def test_neg_broad_except_real_handling():
    """a broad except that does real handling (logs, returns False) is not a swallow -> silent."""
    body = "def verify_seal(s):\n    try:\n        return _check(s)\n    except Exception:\n        log.error('seal failed')\n        return False\n"
    assert not _fires(_P, body)


def test_neg_broad_except_swallow_makoto_allow():
    """a documented broad-except degrade-open carrying makoto-allow -> silent (the escape)."""
    body = "def verify_seal(s):\n    try:\n        return _check(s)\n    except Exception:\n        return True  # makoto-allow: degrade-open, optional backend\n"
    assert not _fires(_P, body)


def test_neg_assert_real_condition():
    """`assert <non-const>` is a real assertion, not a tautology -> silent."""
    assert not _fires(_P, "def validate_policy(p):\n    assert p.is_valid()\n")


def test_neg_specific_except_pass_off_broad():
    """`except ImportError: pass` (optional import) is specific, not broad -> silent."""
    assert not _fires(_P, "def check_x(s):\n    try:\n        import fast_lib\n    except ImportError:\n        pass\n")
