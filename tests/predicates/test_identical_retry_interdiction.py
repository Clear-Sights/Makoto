"""D1 (docs/DEFERRED.md): red-before-green + FP-guard battery for
event.identical_retry (checks/identicalRetryInterdiction.py). Proves the ship-bar directly: a
deterministic-failure retry blocks; a transient-failure retry (the KNOWN FP class the whole
design exists to avoid) never does; an intervening action always breaks the match; a
non-identical retry never fires.
"""
from __future__ import annotations

from makoto.checks.identicalRetryInterdiction import predicate
from makoto.core.schema import PreCheck

PATTERN = PreCheck(id="event.identical_retry", fire_level="error", description="x", retry_hint="y")


def _post_row(command: str, stdout: str) -> dict:
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": command},
                        "tool_response": {"stdout": stdout, "stderr": "", "exitCode": 1}}}


def _pre_event(command: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}}


def test_fires_on_identical_retry_after_deterministic_failure():
    history = [_post_row("python3 nonexistent.py", "No such file or directory")]
    finding = predicate(current_event=_pre_event("python3 nonexistent.py"), history=history,
                        pattern=PATTERN)
    assert finding is not None
    assert finding.pattern_id == "event.identical_retry"


def test_silent_on_identical_retry_after_transient_failure():
    """THE ship-bar case: a real re-poll of a timeout/connection-refused/5xx must NEVER block --
    this is the exact known-FP class both Fable consultations named."""
    history = [_post_row("curl https://api.example.com/status", "Connection refused")]
    finding = predicate(current_event=_pre_event("curl https://api.example.com/status"),
                        history=history, pattern=PATTERN)
    assert finding is None


def test_silent_on_identical_retry_after_ambiguous_failure():
    history = [_post_row("some-tool run", "exit status 1")]   # no marker either way -- uncertain
    finding = predicate(current_event=_pre_event("some-tool run"), history=history, pattern=PATTERN)
    assert finding is None


def test_silent_when_command_changed():
    history = [_post_row("python3 nonexistent.py", "No such file or directory")]
    finding = predicate(current_event=_pre_event("python3 different_file.py"), history=history,
                        pattern=PATTERN)
    assert finding is None


def test_silent_when_an_intervening_call_happened():
    """Structural enforcement of 'no intervening state change': the failing call is no longer
    the MOST RECENT row once anything else happened -- it can never match, by construction."""
    history = [
        _post_row("python3 nonexistent.py", "No such file or directory"),
        {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Write",
                     "tool_input": {"file_path": "nonexistent.py"}, "tool_response": {}}},
    ]
    finding = predicate(current_event=_pre_event("python3 nonexistent.py"), history=history,
                        pattern=PATTERN)
    assert finding is None


def test_silent_on_first_ever_call_no_history():
    finding = predicate(current_event=_pre_event("python3 x.py"), history=[], pattern=PATTERN)
    assert finding is None


def test_silent_on_non_bash_tool():
    history = [_post_row("python3 nonexistent.py", "No such file or directory")]
    event = {"hook_event_name": "PreToolUse", "tool_name": "Write",
             "tool_input": {"file_path": "x"}}
    assert predicate(current_event=event, history=history, pattern=PATTERN) is None


def test_silent_when_prior_call_was_a_different_tool():
    history = [{"payload": {"hook_event_name": "PostToolUse", "tool_name": "Read",
                            "tool_input": {"file_path": "x"}, "tool_response": {}}}]
    finding = predicate(current_event=_pre_event("python3 x.py"), history=history, pattern=PATTERN)
    assert finding is None
