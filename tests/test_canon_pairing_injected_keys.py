"""Only terminal rows are calls, and verdicts key on the full `canon_input`. A harness may add
bookkeeping keys to `tool_input` between a call's PreToolUse and its PostToolUse; the Post is the
call, with the keys it carries, and a Pre with no terminal is nothing. The true-positive cases
below hold the line that this never discharges a genuine run of failures."""
from __future__ import annotations

import json

from makoto.checks.canonTimeoutRecur import (
    canon_input,
    _pairing_input,
    calls_from_history,
    fired_primitives,
    recur_stuck,
)

BASE = {"file_path": "/x", "content": "c", "mode": "w"}
INJECTED = {**BASE, "__artifactPlanConsentAsk": True,
            "__artifactPlanConsentDecisionCaps": 2, "__artifactPublishTarget": "gallery"}


def _row(event, tool, tool_input, *, error=False):
    payload = {"hook_event_name": event, "tool_name": tool, "tool_input": tool_input}
    if event == "PostToolUse":
        payload["tool_response"] = {"error_code": 1} if error else {"ok": True}
    return (1, "ts", event, "/repo", json.dumps(payload))


def _stream(calls):
    return "".join("E" if c["result"].get("interrupted") else "o" for c in calls)


# ---- the pairing identity ---------------------------------------------------------------------
def test_pairing_input_ignores_leading_dunder_keys():
    assert _pairing_input(BASE) == _pairing_input(INJECTED)


def test_the_verdict_identity_still_sees_them():
    """PAIRED. Only pairing is dunder-insensitive; `canon_input` -- what every verdict keys on --
    is unchanged, so the relaxation cannot leak into a judgment."""
    assert canon_input(BASE) != canon_input(INJECTED)


def test_pairing_input_never_collapses_genuinely_distinct_calls():
    """PAIRED REFUSAL. A leading `__` is a transport convention, never call semantics -- so
    dropping it must not make two different calls look like one."""
    assert _pairing_input({"command": "a"}) != _pairing_input({"command": "b"})
    assert _pairing_input("scalar") == canon_input("scalar")


# ---- the four shapes from the report ----------------------------------------------------------
def test_the_reported_false_positive_no_longer_fires():
    """Shape 1: first call drops its Post (dead socket), second SUCCEEDS but its Post carries the
    injected keys. Decoded `EEoo` before the fix -> STUCK on a turn that worked."""
    history = [_row("PreToolUse", "Artifact", BASE),
               _row("PreToolUse", "Artifact", BASE),
               _row("PostToolUse", "Artifact", INJECTED),
               _row("PreToolUse", "Read", {"file_path": "/y"}),
               _row("PostToolUse", "Read", {"file_path": "/y"})]
    calls = calls_from_history(history)
    assert _stream(calls) == "oo", _stream(calls)
    assert recur_stuck(calls) is False


def test_the_same_shape_without_injection_was_already_correct():
    history = [_row("PreToolUse", "Artifact", BASE),
               _row("PreToolUse", "Artifact", BASE),
               _row("PostToolUse", "Artifact", BASE),
               _row("PreToolUse", "Read", {"file_path": "/y"}),
               _row("PostToolUse", "Read", {"file_path": "/y"})]
    assert recur_stuck(calls_from_history(history)) is False


def test_two_successful_injected_calls_are_silent():
    history = [_row("PreToolUse", "Artifact", BASE), _row("PostToolUse", "Artifact", INJECTED),
               _row("PreToolUse", "Artifact", BASE), _row("PostToolUse", "Artifact", INJECTED)]
    calls = calls_from_history(history)
    assert _stream(calls) == "oo"
    assert recur_stuck(calls) is False


def test_a_lone_dangling_pre_is_still_silent():
    assert recur_stuck(calls_from_history([_row("PreToolUse", "Bash", {"command": "x"})])) is False


# ---- the true positives that must keep firing -------------------------------------------------
def test_a_byte_identical_command_failing_twice_still_fires():
    history = [_row("PreToolUse", "Bash", {"command": "x"}),
               _row("PostToolUse", "Bash", {"command": "x"}, error=True),
               _row("PreToolUse", "Bash", {"command": "x"}),
               _row("PostToolUse", "Bash", {"command": "x"}, error=True)]
    assert recur_stuck(calls_from_history(history)) is True


def test_a_command_failing_three_times_still_fires():
    history = []
    for _ in range(3):
        history += [_row("PreToolUse", "Bash", {"command": "y"}),
                    _row("PostToolUse", "Bash", {"command": "y"}, error=True)]
    assert recur_stuck(calls_from_history(history)) is True


def test_two_adjacent_dangling_pres_are_silent():
    """A Pre with no terminal is not a call: declined, abandoned and running look alike."""
    history = [_row("PreToolUse", "Bash", {"command": "z"}),
               _row("PreToolUse", "Bash", {"command": "z"}),
               _row("PreToolUse", "Read", {"file_path": "/y"}),
               _row("PostToolUse", "Read", {"file_path": "/y"})]
    assert recur_stuck(calls_from_history(history)) is False


# ---- every fired primitive names a reachable discharge ----------------------------------------
def test_every_fired_primitive_names_its_release_operator_discharge():
    """`canon_gate` offers the ackblock discharge to EVERY fired primitive, but the affordance was
    spelled out only in `timeout`'s hand-written hint. A fired `canon.recur` therefore named no
    reachable way out, so a false positive re-fired at every subsequent Stop until the rows aged
    out of the recency window. A mechanism that exists but is invisible reads exactly like a
    mechanism that is missing, so the clause is generated per id rather than written per entry."""
    history = [_row("PreToolUse", "Bash", {"command": "q"}),
               _row("PostToolUse", "Bash", {"command": "q"}, error=True),
               _row("PreToolUse", "Bash", {"command": "q"}),
               _row("PostToolUse", "Bash", {"command": "q"}, error=True)]
    fired = list(fired_primitives(history))
    assert {cid for cid, _, _ in fired} == {"timeout", "recur"}
    for cid, _stop_text, retry_hint in fired:
        assert f"makoto release.operator {cid}:" in retry_hint, cid
