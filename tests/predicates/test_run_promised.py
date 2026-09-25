"""gate.run_promised: last turn's promised run with no Bash call since blocks; anything else is silent."""
from __future__ import annotations

import json

import pytest

from makoto.checks.switch import run_promised_gate


def _row(ev):
    return {"payload": json.dumps(ev)}


def _stop(text):
    return _row({"hook_event_name": "Stop", "last_assistant_message": text})


BASH = _row({"hook_event_name": "PostToolUse", "tool_name": "Bash",
             "tool_input": {"command": "pytest"}, "tool_response": {"stdout": "1 passed"}})
FAILED_BASH = _row({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
                    "tool_input": {"command": "pytest"}, "error": "exit 1"})


@pytest.mark.parametrize("text", [
    "I'll run all 602 checks now.",          # f2 of the probe: promised, then nothing ran
    "I'll rerun all 602.",
    "Let me run the suite.",
    "I'm going to restart the server.",
])
def test_promise_with_no_run_blocks(text):
    f = run_promised_gate(history=[_stop(text)])
    assert f is not None and f.pattern_id == "gate.run_promised"


@pytest.mark.parametrize("text", [
    "I propose we rerun all 602.",           # a proposal, not a promise
    "Should I run the tests?",
    "I'll never run that.",
    'He wrote "I\'ll run it" in the log.',
    "I'll run it by you first.",
    "Done.",
])
def test_no_promise_is_silent(text):
    assert run_promised_gate(history=[_stop(text)]) is None


@pytest.mark.parametrize("ran", [BASH, FAILED_BASH])
def test_any_bash_after_the_promise_discharges_it(ran):
    assert run_promised_gate(history=[_stop("I'll run the tests."), ran]) is None


def test_a_run_before_the_promise_does_not_discharge_it():
    assert run_promised_gate(history=[BASH, _stop("I'll run the tests.")]) is not None


def test_no_prior_turn_is_silent():
    assert run_promised_gate(history=[BASH]) is None
