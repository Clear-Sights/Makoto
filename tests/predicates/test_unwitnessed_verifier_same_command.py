"""gate.unwitnessed_verifier: only a failing run of the same verifier pays for its clean run."""
from __future__ import annotations

import json

import pytest

from makoto.checks.switch import unwitnessed_verifier_gate


def _run(cmd, out, code=0):
    return {"payload": json.dumps({
        "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": cmd},
        "tool_response": {"stdout": out, "stderr": "", "exitCode": code}})}


PROBE = "python3 zero/tests/probe.py G"


@pytest.mark.parametrize("history", [
    [_run(PROBE, "G PASS")],                                          # a tree's own check script
    [_run("bash zero/tests/run.sh", "every test PASS")],
    [_run("pytest -q", "1 failed, 3 passed", 1), _run(PROBE, "G PASS")],  # another one's red
    [_run(PROBE, "G PASS"), _run(PROBE, "G FAIL", 1)],                # red only after the clean run
])
def test_clean_run_never_seen_red_fires(history):
    assert unwitnessed_verifier_gate(history) is not None


@pytest.mark.parametrize("history", [
    [_run(PROBE, "G FAIL", 1), _run(PROBE, "G PASS")],
    [_run("pytest -x", "1 failed", 1), _run("pytest -q | tail -n 3", "5 passed")],
    [_run("# keel-guard: U08\npytest", "1 failed", 1), _run("pytest 2>&1", "5 passed")],
    [_run("cat zero/tests/probe.py", "PASS")],                        # reading a check runs nothing
])
def test_same_verifier_seen_red_or_no_verifier_is_silent(history):
    assert unwitnessed_verifier_gate(history) is None
