"""gate.unwitnessed_verifier (register B4 WRONG ORACLE): a clean report from a verifier this
session has never seen fail blocks the stop until the same verifier is seen red."""
from __future__ import annotations

from makoto.checks.switch import unwitnessed_verifier_gate


def _bash(command, stdout=""):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": command},
                        "tool_response": {"stdout": stdout, "exitCode": 0}}}


# gate.unwitnessed_verifier (register B4 WRONG ORACLE)

def test_unwitnessed_verifier_fires_on_a_first_clean_run():
    f = unwitnessed_verifier_gate([_bash("pytest -q", "58 passed in 2.0s")])
    assert f is not None and f.level == "error"


def test_unwitnessed_verifier_is_silent_once_the_verifier_has_been_seen_failing():
    assert unwitnessed_verifier_gate([_bash("pytest -q", "1 failed, 57 passed"),
                                      _bash("pytest -q", "58 passed")]) is None


def test_unwitnessed_verifier_still_fires_when_the_red_run_came_after():
    assert unwitnessed_verifier_gate([_bash("pytest -q", "58 passed"),
                                      _bash("pytest -q", "1 failed")]) is not None


def test_unwitnessed_verifier_reads_zero_failed_as_a_clean_report():
    """The regression this test exists for: `re.I` over `\\bFAILED\\b` matched the WORD "failed",
    so "58 passed, 0 failed" read as the verifier FIRING and the gate went quiet on exactly the
    report it exists for. The counted form is anchored to a non-zero count and the bare report
    tokens are case-sensitive."""
    assert unwitnessed_verifier_gate([_bash("pytest -q", "58 passed, 0 failed")]) is not None


def test_unwitnessed_verifier_is_silent_on_a_command_that_is_not_a_verifier():
    assert unwitnessed_verifier_gate([_bash("ls -la", "OK")]) is None
