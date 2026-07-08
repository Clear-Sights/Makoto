"""Tests for FD14-A (narrowed to MID-TURN ABANDONMENT ONLY): `canon.calls_from_history` synthesizes
a FAILURE Call for a dangling PreToolUse (one with no matching PostToolUse) ONLY when it is NOT the
chronologically last tool-related row before Stop -- i.e. some OTHER decoded row (Pre or Post, any
tool) occurred after it and it was still never resolved.

This scope was narrowed by owner decision (via AskUserQuestion, this session -- see
EXECUTION_PLAN.md / docs/superpowers/plans/2026-07-06-spec4-makoto.md for the FD14-A ticket text)
to resolve a direct conflict with `test_dispatch.py::test_dispatch_fabricated_action_silent_when_
command_ran`, which pins that a SINGLE dangling Pre that IS the last tool-related row before Stop
must mean "presence of work, discharge the claim" -- NOT a failure. FD14-A's actual target is a
tool call that was fired and abandoned mid-turn while the agent moved on to something else, in an
environment where PostToolUse does not reliably fire on failure/interruption.

Complements test_canon_primitives.py (pure predicate/decode unit tests, pre-existing) and
test_gate_canon_live_battery.py (anti-Goodhart RED/TN battery through run_stop_checks). This file
adds: (1) pure calls_from_history unit tests pinning the narrowed synthesis rule directly, and
(2) end-to-end dispatch tests (mirroring test_dispatch.py's `_run_dispatch` subprocess pattern)
proving gate.canon actually fires/blocks live on a mid-turn-abandoned call, and stays silent on the
last-row-discharge shape."""
import json
import os
import subprocess
import sys
from pathlib import Path

from makoto.checks.canonTimeoutRecur import calls_from_history, timed_out_at_turn_end


# ---- pure calls_from_history unit tests: the narrowed synthesis rule --------------------------
def _tuple_row(idx, event_type, tool_name, tool_input, tool_response, cwd="/repo"):
    payload = json.dumps({"hook_event_name": event_type, "tool_name": tool_name,
                           "tool_input": tool_input, "tool_response": tool_response})
    return (idx, "t", event_type, cwd, payload)


def test_dangling_pre_as_last_row_is_not_synthesized():
    """A single dangling Pre that IS the last tool-related row before Stop -> no Call at all (the
    presence-of-work discharge case; matches unmodified pre-FD14-A behavior for this shape)."""
    row = _tuple_row(1, "PreToolUse", "Bash", {"command": "long-running-thing"}, {})
    assert calls_from_history([row]) == []


def test_dangling_pre_followed_by_another_unresolved_row_is_synthesized_as_failure():
    """Mid-turn abandonment: a dangling Pre (A) followed by ANOTHER dangling Pre (B) later in
    history -- B is itself never resolved either, but A is no longer the last tool-related row, so
    A synthesizes a failure Call. B, now the last decoded row, is left out (not synthesized) --
    exactly one Call results, and it is A's synthesized failure."""
    pre_a = _tuple_row(1, "PreToolUse", "Bash", {"command": "cmd-a"}, {})
    pre_b = _tuple_row(2, "PreToolUse", "Bash", {"command": "cmd-b"}, {})
    calls = calls_from_history([pre_a, pre_b])
    assert len(calls) == 1
    assert calls[0]["name"] == "Bash"
    assert calls[0]["input"] == {"command": "cmd-a"}
    assert calls[0]["result"].get("interrupted") is True
    # the synthesized failure is the only (and therefore last) Call -> canon.timeout must see it.
    assert timed_out_at_turn_end(calls) is True


def test_dangling_pre_followed_by_a_resolved_post_of_a_different_tool_is_synthesized():
    """The "something else happened after it" row need not itself be unresolved -- a completed,
    successful, unrelated call occurring after the dangling Pre still counts as evidence the agent
    moved on, per the ticket's "Pre or Post, any tool" wording."""
    pre_a = _tuple_row(1, "PreToolUse", "Bash", {"command": "cmd-a"}, {})
    pre_read = _tuple_row(2, "PreToolUse", "Read", {"file_path": "x.py"}, {})
    post_read = _tuple_row(3, "PostToolUse", "Read", {"file_path": "x.py"}, {"stdout": "ok"})
    calls = calls_from_history([pre_a, pre_read, post_read])
    # exactly two Calls: the synthesized failure for cmd-a, and the real completed Read.
    assert len(calls) == 2
    assert calls[0]["name"] == "Bash" and calls[0]["result"].get("interrupted") is True
    assert calls[1] == {"name": "Read", "input": {"file_path": "x.py"}, "result": {"stdout": "ok"}}


def test_normal_fully_paired_call_is_unaffected():
    """A completed Pre+Post pair still becomes exactly one Call, from the Post -- the pairing
    logic (lifted structurally from the reference stash) is not disturbed by the mid-turn gate."""
    pre = _tuple_row(1, "PreToolUse", "Bash", {"command": "x"}, {})
    post = _tuple_row(2, "PostToolUse", "Bash", {"command": "x"}, {"stdout": "ok"})
    assert calls_from_history([pre, post]) == [
        {"name": "Bash", "input": {"command": "x"}, "result": {"stdout": "ok"}}]


# ---- end-to-end, through the real dispatch (mirrors test_dispatch.py's _run_dispatch pattern) --
def _setup_state(tmp_path):
    """create a makoto.db with the 3 tables + minimal config; return state_dir."""
    from makoto.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n")
    init_db(state_dir, citations)
    return state_dir


def _run_dispatch(state_dir, payload: dict, extra_env: dict | None = None) -> tuple[int, str]:
    """invoke `python -m makoto._dispatch` with payload on stdin; return (exit, stdout)."""
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    return proc.returncode, proc.stdout.decode("utf-8")


def test_dispatch_last_row_dangling_pre_stays_silent_no_block(tmp_path):
    """Same shape as test_dispatch.py::test_dispatch_fabricated_action_silent_when_command_ran, but
    exercised directly against gate.canon's own verdict: a single dangling PreToolUse (Bash) with
    no PostToolUse, then Stop with nothing else in between -> it IS the last tool-related row ->
    no failure synthesized -> canon.timeout does not fire, no block."""
    state_dir = _setup_state(tmp_path)
    pre = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "midturn_last",
           "cwd": str(tmp_path),
           "tool_input": {"command": "python -m pytest tests/zzz_unrun.py -q"}}
    _run_dispatch(state_dir, pre)
    stop = {"hook_event_name": "Stop", "session_id": "midturn_last", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", "a dangling Pre that is the last tool row before Stop must not block"


def test_dispatch_mid_turn_abandoned_pre_synthesizes_failure_and_canon_blocks(tmp_path):
    """Mid-turn abandonment fires canon.timeout live: a PreToolUse (Bash, cmd-a) never gets a
    PostToolUse, but the agent moves on to ANOTHER PreToolUse (Bash, cmd-b) -- itself also never
    resolved -- before Stop. cmd-a is no longer the last tool-related row, so it synthesizes a
    failure Call; that failure becomes the turn's last Call (cmd-b, being the new last row, is
    left un-synthesized) -> canon.timeout fires -> gate.canon blocks by default, exactly like
    test_dispatch.py::test_dispatch_canon_gate_blocks_by_default's PostToolUse-interrupted case."""
    state_dir = _setup_state(tmp_path)
    sid = "midturn_abandon"
    pre_a = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": sid,
             "cwd": str(tmp_path), "tool_input": {"command": "cmd-a-never-resolved"}}
    pre_b = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": sid,
             "cwd": str(tmp_path), "tool_input": {"command": "cmd-b-also-never-resolved"}}
    rc, out = _run_dispatch(state_dir, pre_a)
    assert rc == 0 and out == ""
    rc, out = _run_dispatch(state_dir, pre_b)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "a mid-turn-abandoned dangling Pre must synthesize a failure and block via canon.timeout"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "canon.timeout" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.canon" in r.get("pattern_fires", []) for r in rows), \
        "the gate.canon fire must be audited"


def test_dispatch_normal_paired_call_unaffected_no_block(tmp_path):
    """A normal, fully-paired Pre+Post call (real success) is unaffected by the FD14-A synthesis
    rule -- still exactly one Call from the Post, no block."""
    state_dir = _setup_state(tmp_path)
    sid = "midturn_paired_ok"
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
            "cwd": str(tmp_path), "tool_input": {"command": "echo hi"},
            "tool_response": {"stdout": "hi\n", "stderr": "", "exitCode": 0}}
    rc, out = _run_dispatch(state_dir, post)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", "a normal completed call must not be affected by the dangling-pre synthesis rule"
