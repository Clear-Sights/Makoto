"""A PreToolUse row with no terminal is not a call. An owner-declined call, an abandoned one and
one still running leave the same trace, and `calls_from_history` yields nothing for any of them.
This file pins that directly and through dispatch: no Call is synthesized, so gate.canon stays
silent on a dangling Pre wherever it sits, and a fully paired call still becomes one Call."""
import json

from makoto.checks.canonTimeoutRecur import calls_from_history, canon_gate, timed_out_at_turn_end


# ---- pure calls_from_history unit tests: the narrowed synthesis rule --------------------------
def _tuple_row(idx, event_type, tool_name, tool_input, tool_response, cwd="/repo"):
    payload = json.dumps({"hook_event_name": event_type, "tool_name": tool_name,
                           "tool_input": tool_input, "tool_response": tool_response})
    return (idx, "t", event_type, cwd, payload)


def test_a_pre_with_no_terminal_is_no_call():
    """An owner-declined call, an abandoned one and a running one leave the same trace: a
    PreToolUse with no terminal. None is a failure; none is a call."""
    history = [_tuple_row(1, "PreToolUse", "ExitPlanMode", {}, {}),
               _tuple_row(2, "PreToolUse", "ExitPlanMode", {}, {}),
               _tuple_row(3, "PreToolUse", "Bash", {"command": "cmd"}, {})]
    assert calls_from_history(history) == []
    assert canon_gate(history) == []


def test_normal_fully_paired_call_is_unaffected():
    """A completed Pre+Post pair still becomes exactly one Call, from the Post -- the pairing
    logic (lifted structurally from the reference stash) is not disturbed by the mid-turn gate."""
    pre = _tuple_row(1, "PreToolUse", "Bash", {"command": "x"}, {})
    post = _tuple_row(2, "PostToolUse", "Bash", {"command": "x"}, {"stdout": "ok"})
    assert calls_from_history([pre, post]) == [
        {"name": "Bash", "input": {"command": "x"}, "result": {"stdout": "ok"}}]


# ---- end-to-end, through the real dispatch (mirrors test_dispatch.py's _run_dispatch pattern) --
def test_dispatch_last_row_dangling_pre_stays_silent_no_block(state_dir, run_dispatch, tmp_path):
    """Same shape as test_dispatch.py::test_dispatch_fabricated_action_silent_when_command_ran, but
    exercised directly against gate.canon's own verdict: a single dangling PreToolUse (Bash) with
    no PostToolUse, then Stop with nothing else in between -> it IS the last tool-related row ->
    no failure synthesized -> canon.timeout does not fire, no block."""
    pre = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "midturn_last",
           "cwd": str(tmp_path),
           "tool_input": {"command": "python -m pytest tests/zzz_unrun.py -q"}}
    run_dispatch(state_dir, pre)
    stop = {"hook_event_name": "Stop", "session_id": "midturn_last", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = run_dispatch(state_dir, stop)
    assert out == "", "a dangling Pre that is the last tool row before Stop must not block"


def test_dispatch_mid_turn_abandoned_pre_is_silent(state_dir, run_dispatch, tmp_path):
    """Two PreToolUse rows with no terminal, then Stop: nothing is synthesized, nothing blocks."""
    sid = "midturn_abandon"
    for command in ("cmd-a-never-resolved", "cmd-b-also-never-resolved"):
        rc, out = run_dispatch(state_dir, {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": sid,
                                           "cwd": str(tmp_path), "tool_input": {"command": command}})
        assert rc == 0 and out == ""
    rc, out = run_dispatch(state_dir, {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
                                       "last_assistant_message": "Done for now."})
    assert out == "", "a Pre with no terminal is no call and must not block"


def test_dispatch_normal_paired_call_unaffected_no_block(state_dir, run_dispatch, tmp_path):
    """A normal, fully-paired Pre+Post call (real success) is unaffected by the FD14-A synthesis
    rule -- still exactly one Call from the Post, no block."""
    sid = "midturn_paired_ok"
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
            "cwd": str(tmp_path), "tool_input": {"command": "echo hi"},
            "tool_response": {"stdout": "hi\n", "stderr": "", "exitCode": 0}}
    rc, out = run_dispatch(state_dir, post)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = run_dispatch(state_dir, stop)
    assert out == "", "a normal completed call must not be affected by the dangling-pre synthesis rule"
