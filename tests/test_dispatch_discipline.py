"""PROPOSED-REGISTER-ROWS.md's dispatch-discipline rows -- I1/event.unbriefed_dispatch,
I2/event.unpinned_input, I3/gate.unpaid_acceptance. All three are opt-in: silent unless the
session's own working tree declares `dispatch = true` in its `makoto.toml`.
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


def test_unbriefed_silent_on_bare_prose_when_not_opted_in(tmp_path):
    _no_opt_in(tmp_path)
    assert unbriefed_predicate(current_event=_agent_event(tmp_path, BARE_PROMPT),
                               history=[], pattern=unbriefed_CHECK) is None


def test_unbriefed_silent_on_the_full_brief_even_opted_in(tmp_path):
    _opt_in(tmp_path)
    assert unbriefed_predicate(current_event=_agent_event(tmp_path, FULL_PROMPT),
                               history=[], pattern=unbriefed_CHECK) is None


# ---- event.unpinned_input (I2, OTHER_POINT) ----------------------------------------------------

def test_unpinned_fires_on_an_unhashed_read_path_when_opted_in(tmp_path):
    _opt_in(tmp_path)
    finding = unpinned_predicate(current_event=_agent_event(tmp_path, UNPINNED_READ_PROMPT),
                                 history=[], pattern=unpinned_CHECK)
    assert finding is not None
    assert finding.pattern_id == "event.unpinned_input"
    assert finding.level == "error"


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


def test_unpaid_acceptance_silent_when_it_ran_and_passed(tmp_path):
    transcript = _transcript(tmp_path)
    history = [_dispatch_row(), _paying_bash_row("2026-01-01T00:00:02.000000Z", exit_code=0)]
    assert unpaid_acceptance_gate(history, transcript_path=transcript) is None


def test_unpaid_acceptance_silent_when_dispatch_is_this_turn_in_flight(tmp_path):
    """No operator turn between the dispatch and Stop -- nothing is PROVEN prior-turn."""
    assert unpaid_acceptance_gate([_dispatch_row()], transcript_path=None) is None


def test_unpaid_acceptance_check_is_silent_when_not_opted_in(tmp_path):
    from makoto.context import GateContext
    transcript = _transcript(tmp_path)
    ctx = GateContext(text="Done.", touched=frozenset(), empty=frozenset(), testrun_output="",
                      cwd=str(tmp_path), fs_exists=lambda p: False, fs_size=lambda p: None,
                      fs_read=lambda p: None, history=[_dispatch_row()],
                      transcript_path=transcript, stop_hook_active=False)
    dispatch_opt_in.cache_clear()
    assert unpaid_CHECK.run(ctx) is None


def test_unpaid_acceptance_check_bounces_once_on_stop_hook_active(tmp_path):
    """BLOCK gets no automatic wire-level suppression on stop_hook_active, so this row takes its
    own one bounce."""
    from makoto.context import GateContext
    _opt_in(tmp_path)
    transcript = _transcript(tmp_path)
    ctx = GateContext(text="Done.", touched=frozenset(), empty=frozenset(), testrun_output="",
                      cwd=str(tmp_path), fs_exists=lambda p: False, fs_size=lambda p: None,
                      fs_read=lambda p: None, history=[_dispatch_row()],
                      transcript_path=transcript, stop_hook_active=True)
    assert unpaid_CHECK.run(ctx) is None
