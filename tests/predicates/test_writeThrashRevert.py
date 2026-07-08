"""CANON-PORT-1 falsifier for event.thrash_revert: an A->B->A whole-file Write self-revert fires;
A->B->C progress and a bare A->A repeat stay silent; a current Edit/MultiEdit fragment is never
judged (the canon.oscillate 7-FP lesson); whitespace-only differences are the same content."""
import json

from makoto.schema import Finding, PreCheck
from makoto.checks.writeThrashRevert import predicate

_PAT = PreCheck(
    id="event.thrash_revert", fire_level="error",
    description="whole-file A->B->A self-revert",
    retry_hint="change the input or commit one version", keywords=["thrash"],
)


def _write_row(idx, path, content):
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                          "tool_input": {"file_path": path, "content": content}})
    return (idx, "t", "PreToolUse", "/repo", payload)


def _cur(path, content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": path, "content": content}}


def test_fires_on_A_B_A_whole_file_revert():
    hist = [_write_row(1, "f.py", "A"), _write_row(2, "f.py", "B")]
    f = predicate(current_event=_cur("f.py", "A"), history=hist, pattern=_PAT)
    assert isinstance(f, Finding)
    assert f.pattern_id == "event.thrash_revert"


def test_silent_on_A_B_C_progress():
    hist = [_write_row(1, "f.py", "A"), _write_row(2, "f.py", "B")]
    assert predicate(current_event=_cur("f.py", "C"), history=hist, pattern=_PAT) is None


def test_silent_on_bare_A_A_repeat_with_no_intervening_change():
    hist = [_write_row(1, "f.py", "A")]
    assert predicate(current_event=_cur("f.py", "A"), history=hist, pattern=_PAT) is None


def test_silent_when_current_is_a_fragment_edit_not_a_whole_file_write():
    hist = [_write_row(1, "f.py", "A"), _write_row(2, "f.py", "B")]
    edit = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": "f.py", "new_string": "A"}}
    assert predicate(current_event=edit, history=hist, pattern=_PAT) is None


def test_whitespace_normalized_identity_still_counts_as_revert():
    hist = [_write_row(1, "f.py", "A   x"), _write_row(2, "f.py", "B")]
    f = predicate(current_event=_cur("f.py", "A x"), history=hist, pattern=_PAT)
    assert isinstance(f, Finding)     # ByteIdentity collapses whitespace runs -> same content