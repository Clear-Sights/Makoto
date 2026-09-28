"""gate.option_interaction (E8): the cases an adversarial read found, each kept as a plant."""
from __future__ import annotations

import json

from makoto.checks.switch import option_interaction_gate as gate


def _row(tool, ti, rc=0, hook="PostToolUse"):
    return {"payload": json.dumps({"hook_event_name": hook, "tool_name": tool, "tool_input": ti,
                                   "tool_response": {"stdout": "", "exitCode": rc}}),
            "event_type": "PostToolUse"}


def _bash(cmd, rc):
    return _row("Bash", {"command": cmd}, rc)


def _write(path, content, hook="PostToolUse"):
    return _row("Write", {"file_path": path, "content": content}, hook=hook)


RED_GREEN = [_bash("X=1 tool", 1), _bash("X=1 Y=2 tool", 0)]


def test_a_gained_option_is_owed_and_a_write_carrying_it_pays():
    assert gate(RED_GREEN) is not None
    assert gate(RED_GREEN + [_write("config.env", "Y=2\n")]) is None
    assert gate(RED_GREEN + [_write("c.yml", "Y: 2\n")]) is None


def test_a_write_before_the_passing_run_does_not_pay():
    assert gate([_write("config.env", "Y=2\n")] + RED_GREEN) is not None


def test_a_failed_write_and_a_wrong_value_do_not_pay():
    assert gate(RED_GREEN + [_write("config.env", "Y=2\n", hook="PostToolUseFailure")]) is not None
    assert gate(RED_GREEN + [_write("config.env", "Y=20\n")]) is not None


def test_a_dropped_option_is_owed_and_editing_it_out_pays():
    h = [_bash("pytest --strict-markers", 1), _bash("pytest", 0)]
    assert gate(h) is not None
    assert gate(h + [_row("Edit", {"file_path": "pytest.ini", "old_string": "addopts = --strict-markers\n",
                                   "new_string": "addopts =\n"})]) is None


def test_a_repeated_option_is_owed():
    assert gate([_bash("ssh -t host tty", 1), _bash("ssh -t -t host tty", 0)]) is not None


def test_option_shaped_text_inside_quotes_is_not_an_option():
    assert gate([_bash("grep 'error --strict failure' log.txt", 1),
                 _bash("grep 'error --lenient failure' log.txt", 0)]) is None


def test_a_passing_run_then_a_failing_one_owes_nothing():
    assert gate([_bash("X=1 Y=2 tool", 0), _bash("X=1 tool", 1)]) is None
