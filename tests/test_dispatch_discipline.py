"""PROPOSED-REGISTER-ROWS.md's dispatch-discipline rows -- I1/event.unbriefed_dispatch,
I2/event.unpinned_input, I3/gate.unpaid_acceptance. All three are opt-in: silent unless the
session's own working tree declares `dispatch = true` in its `makoto.toml`
(`core._declaredverifiers.dispatch_opt_in`, the same declaration file/parser the verifier tier
already reads, generalized rather than duplicated).

Each group below: fires when opted in, silent when not opted in (same input), and the full-brief
pass case is silent even opted in.
"""
from __future__ import annotations

import json

from makoto.checks.lineage import unbriefed_CHECK, unbriefed_predicate
from makoto.checks.otherPoint import unpinned_CHECK, unpinned_predicate
from makoto.checks.otherPoint import unpaid_CHECK, unpaid_acceptance_gate
from makoto.core._declaredverifiers import dispatch_opt_in


def _opt_in(tmp_path):
    (tmp_path / "makoto.toml").write_text("dispatch = true\n")
    dispatch_opt_in.cache_clear()


def _no_opt_in(tmp_path):
    dispatch_opt_in.cache_clear()


BARE_PROMPT = "Fix the off-by-one in kit.unwitnessed and make the tests pass."
LOOSE_PROMPT = "Reads: kit.py. Then fix it; tests should pass."
FULL_PROMPT = ("READ: plugin/makoto/kit.py@3f2a9c1e0b7d\n"
               "WRITE: plugin/makoto/kit.py\n"
               "ACCEPTANCE: python3 -m pytest -q tests/test_kit.py\n"
               "Fix the off-by-one in unwitnessed.")
UNPINNED_READ_PROMPT = ("READ: plugin/makoto/kit.py\n"
                        "WRITE: plugin/makoto/kit.py\n"
                        "ACCEPTANCE: python3 -m pytest -q tests/test_kit.py\n"
                        "Fix the off-by-one in unwitnessed.")


def _agent_event(tmp_path, prompt, tool_name="Agent"):
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "cwd": str(tmp_path),
            "tool_input": {"description": "fix", "prompt": prompt}}


def _bash_event(tmp_path, command, timeout):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(tmp_path),
            "tool_input": {"command": command, "timeout": timeout}}


# ---- event.unbriefed_dispatch (I1, LINEAGE) ----------------------------------------------------

def test_unbriefed_fires_on_bare_prose_when_opted_in(tmp_path):
    _opt_in(tmp_path)
    finding = unbriefed_predicate(current_event=_agent_event(tmp_path, BARE_PROMPT),
                                  history=[], pattern=unbriefed_CHECK)
    assert finding is not None
    assert finding.pattern_id == "event.unbriefed_dispatch"
    assert finding.level == "error"


def test_unbriefed_fires_on_loose_labels_and_a_different_tool_when_opted_in(tmp_path):
    _opt_in(tmp_path)
    finding = unbriefed_predicate(current_event=_agent_event(tmp_path, LOOSE_PROMPT, "Task"),
                                  history=[], pattern=unbriefed_CHECK)
    assert finding is not None


def test_unbriefed_silent_on_bare_prose_when_not_opted_in(tmp_path):
    _no_opt_in(tmp_path)
    assert unbriefed_predicate(current_event=_agent_event(tmp_path, BARE_PROMPT),
                               history=[], pattern=unbriefed_CHECK) is None


def test_unbriefed_silent_on_the_full_brief_even_opted_in(tmp_path):
    _opt_in(tmp_path)
    assert unbriefed_predicate(current_event=_agent_event(tmp_path, FULL_PROMPT),
                               history=[], pattern=unbriefed_CHECK) is None


def test_unbriefed_silent_on_a_non_dispatch_tool(tmp_path):
    _opt_in(tmp_path)
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(tmp_path),
          "tool_input": {"command": "ls"}}
    assert unbriefed_predicate(current_event=ev, history=[], pattern=unbriefed_CHECK) is None


# ---- event.unpinned_input (I2, OTHER_POINT) ----------------------------------------------------

def test_unpinned_fires_on_an_unhashed_read_path_when_opted_in(tmp_path):
    _opt_in(tmp_path)
    finding = unpinned_predicate(current_event=_agent_event(tmp_path, UNPINNED_READ_PROMPT),
                                 history=[], pattern=unpinned_CHECK)
    assert finding is not None
    assert finding.pattern_id == "event.unpinned_input"
    assert finding.level == "error"


def test_unpinned_fires_on_an_expensive_unpinned_bash_call_when_opted_in(tmp_path):
    _opt_in(tmp_path)
    finding = unpinned_predicate(
        current_event=_bash_event(tmp_path, "python3 check.py SEED.md", 600000),
        history=[], pattern=unpinned_CHECK)
    assert finding is not None


def test_unpinned_silent_when_sha256sum_c_verifies_pins(tmp_path):
    _opt_in(tmp_path)
    assert unpinned_predicate(
        current_event=_bash_event(tmp_path, "sha256sum -c pins.sha256 && python3 check.py SEED.md",
                                  600000),
        history=[], pattern=unpinned_CHECK) is None


def test_unpinned_silent_when_command_names_a_path_at_hash(tmp_path):
    _opt_in(tmp_path)
    assert unpinned_predicate(
        current_event=_bash_event(tmp_path, "python3 check.py SEED.md@3f2a9c1e0b7d", 600000),
        history=[], pattern=unpinned_CHECK) is None


def test_unpinned_silent_on_a_short_timeout_bash_call(tmp_path):
    _opt_in(tmp_path)
    assert unpinned_predicate(
        current_event=_bash_event(tmp_path, "python3 check.py SEED.md", 1000),
        history=[], pattern=unpinned_CHECK) is None


def test_unpinned_silent_on_an_unhashed_read_path_when_not_opted_in(tmp_path):
    _no_opt_in(tmp_path)
    assert unpinned_predicate(current_event=_agent_event(tmp_path, UNPINNED_READ_PROMPT),
                              history=[], pattern=unpinned_CHECK) is None


def test_unpinned_silent_on_the_pinned_read_path(tmp_path):
    _opt_in(tmp_path)
    assert unpinned_predicate(current_event=_agent_event(tmp_path, FULL_PROMPT),
                              history=[], pattern=unpinned_CHECK) is None


# ---- gate.unpaid_acceptance (I3, OTHER_POINT, through kit.unwitnessed) --------------------------

def _transcript(tmp_path, ts="2026-01-01T00:00:05.000000Z"):
    p = tmp_path / "transcript.jsonl"
    p.write_text(json.dumps({"type": "user", "timestamp": ts,
                             "message": {"role": "user", "content": "status?"}}) + "\n")
    return str(p)


def _dispatch_row(ts="2026-01-01T00:00:00.000000Z", prompt=FULL_PROMPT):
    return {"ts": ts, "payload": {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                                  "tool_input": {"description": "fix", "prompt": prompt}}}


def _paying_bash_row(ts, exit_code=0):
    command = "python3 -m pytest -q tests/test_kit.py"
    return {"ts": ts, "payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                  "tool_input": {"command": command},
                                  "tool_response": {"stdout": "", "stderr": "",
                                                    "exitCode": exit_code}}}


def test_unpaid_acceptance_fires_when_never_run_and_dispatch_is_prior_turn(tmp_path):
    transcript = _transcript(tmp_path)
    finding = unpaid_acceptance_gate([_dispatch_row()], transcript_path=transcript)
    assert finding is not None
    assert finding.pattern_id == "gate.unpaid_acceptance"
    assert finding.level == "error"


def test_unpaid_acceptance_fires_when_it_ran_and_failed(tmp_path):
    transcript = _transcript(tmp_path)
    history = [_dispatch_row(), _paying_bash_row("2026-01-01T00:00:02.000000Z", exit_code=1)]
    assert unpaid_acceptance_gate(history, transcript_path=transcript) is not None


def test_unpaid_acceptance_silent_when_it_ran_and_passed(tmp_path):
    transcript = _transcript(tmp_path)
    history = [_dispatch_row(), _paying_bash_row("2026-01-01T00:00:02.000000Z", exit_code=0)]
    assert unpaid_acceptance_gate(history, transcript_path=transcript) is None


def test_unpaid_acceptance_silent_when_dispatch_is_this_turn_in_flight(tmp_path):
    """No operator turn between the dispatch and Stop -- no boundary at all -- so the worker may
    still be in flight and nothing is PROVEN prior-turn."""
    assert unpaid_acceptance_gate([_dispatch_row()], transcript_path=None) is None


def test_unpaid_acceptance_silent_when_dispatch_is_after_the_last_operator_turn(tmp_path):
    """A boundary IS established, but the dispatch's own ts is at/after it -- this turn's own
    dispatch, still possibly in flight."""
    transcript = _transcript(tmp_path, ts="2026-01-01T00:00:00.000000Z")
    history = [_dispatch_row(ts="2026-01-01T00:00:05.000000Z")]
    assert unpaid_acceptance_gate(history, transcript_path=transcript) is None


def test_unpaid_acceptance_check_is_silent_when_not_opted_in(tmp_path):
    from makoto.context import GateContext
    transcript = _transcript(tmp_path)
    ctx = GateContext(text="Done.", touched=frozenset(), empty=frozenset(), testrun_output="",
                      cwd=str(tmp_path), fs_exists=lambda p: False, fs_size=lambda p: None,
                      fs_read=lambda p: None, history=[_dispatch_row()],
                      transcript_path=transcript, stop_hook_active=False)
    dispatch_opt_in.cache_clear()
    assert unpaid_CHECK.run(ctx) is None


def test_unpaid_acceptance_check_fires_when_opted_in_through_ctx(tmp_path):
    from makoto.context import GateContext
    _opt_in(tmp_path)
    transcript = _transcript(tmp_path)
    ctx = GateContext(text="Done.", touched=frozenset(), empty=frozenset(), testrun_output="",
                      cwd=str(tmp_path), fs_exists=lambda p: False, fs_size=lambda p: None,
                      fs_read=lambda p: None, history=[_dispatch_row()],
                      transcript_path=transcript, stop_hook_active=False)
    assert unpaid_CHECK.run(ctx) is not None


def test_unpaid_acceptance_check_bounces_once_on_stop_hook_active(tmp_path):
    """This row's BLOCK posture gets no automatic wire-level suppression (that's ADVISE-only),
    so it takes its own one bounce: `stop_hook_active` true means this Stop already fired once
    this turn, and the agent gets to actually stop."""
    from makoto.context import GateContext
    _opt_in(tmp_path)
    transcript = _transcript(tmp_path)
    ctx = GateContext(text="Done.", touched=frozenset(), empty=frozenset(), testrun_output="",
                      cwd=str(tmp_path), fs_exists=lambda p: False, fs_size=lambda p: None,
                      fs_read=lambda p: None, history=[_dispatch_row()],
                      transcript_path=transcript, stop_hook_active=True)
    assert unpaid_CHECK.run(ctx) is None
