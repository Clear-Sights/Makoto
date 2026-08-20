"""CANON-PORT-1 falsifier for write.thrash_revert: an A->B->A whole-file Write self-revert fires;
A->B->C progress and a bare A->A repeat stay silent; a current Edit/MultiEdit fragment is never
judged (the canon.oscillate 7-FP lesson); whitespace-only differences are the same content."""
import json

from makoto.vocab import Finding, PreCheck
from makoto.checks.writeThrashRevert import predicate

_PAT = PreCheck(
    id="event.thrash_revert", fire_level="error",
    description="whole-file A->B->A self-revert",
    retry_hint="change the input or commit one version", keywords=["thrash"],
)


def _write_row(idx, path, content, event="PostToolUse"):
    """A LANDED whole-file Write by default: only a successful PostToolUse row proves the disk
    ever held this content. (PreToolUse rows are attempts — possibly denied — and
    PostToolUseFailure rows are writes that did NOT land; neither may serve as the
    intervening B of an A->B->A revert.)"""
    payload = json.dumps({"hook_event_name": event, "tool_name": "Write",
                          "tool_input": {"file_path": path, "content": content}})
    return (idx, "t", event, "/repo", payload)


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

def test_live_catalog_registration_is_reachable_in_dispatch():
    """Every test above drives predicate() through the synthetic _PAT (a test-fixture shape),
    so nothing pinned the LIVE registration: the real CHECK's keywords could be neutered and
    the whole suite stayed green. This pins the live wiring end to end: the catalog entry for
    event.thrash_revert must carry a predicate module, be admitted by dispatch's own keyword
    prefilter for a representative whole-file-Write payload, and fire through that entry."""
    from makoto import dispatch
    from makoto.registry import load_precheck_catalog

    check = next(c for c in load_precheck_catalog() if c.id == "event.thrash_revert")
    assert check.predicate_module, "live check lost its predicate module: unreachable in dispatch"
    cur = _cur("f.py", "A")
    assert dispatch._keyword_hit(check, json.dumps(cur)), (
        "live keywords no longer admit a whole-file Write payload: "
        "event.thrash_revert is unreachable in dispatch")
    hist = [_write_row(1, "f.py", "A"), _write_row(2, "f.py", "B")]
    f = predicate(current_event=cur, history=hist, pattern=check)
    assert isinstance(f, Finding) and f.pattern_id == "event.thrash_revert"


def test_failed_prior_write_is_not_an_intervening_change():
    """A PostToolUseFailure B never landed — disk still holds A, so rewriting A is a no-op
    repeat, not a revert. Counting the failed row as 'the file was changed in between' was a
    DENY resting on a change that never happened."""
    hist = [_write_row(1, "f.py", "A"),
            _write_row(2, "f.py", "B", event="PostToolUseFailure")]
    assert predicate(current_event=_cur("f.py", "A"), history=hist, pattern=_PAT) is None


def test_denied_pretooluse_attempt_is_not_an_intervening_change():
    """`_ingest_event` persists PreToolUse rows before the handler runs, so a DENIED attempt is
    on the record too. It never landed; rewriting the disk's actual content (B) must stay
    allowed, or the check's own retry_hint ('write it once') becomes unreachable."""
    hist = [_write_row(1, "f.py", "A"), _write_row(2, "f.py", "B"),
            _write_row(3, "f.py", "A", event="PreToolUse")]
    assert predicate(current_event=_cur("f.py", "B"), history=hist, pattern=_PAT) is None
