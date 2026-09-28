"""gate.gradient_collapse (A6): the cases an adversarial read found, each kept as a plant."""
from __future__ import annotations

import json

import pytest

from makoto.checks.switch import gradient_collapse_gate as gate


def _row(path, content, tool="Write"):
    ti = {"file_path": path, **content} if tool == "MultiEdit" else {"file_path": path, "content": content}
    return {"payload": json.dumps({"hook_event_name": "PostToolUse", "tool_name": tool,
                                   "tool_input": ti, "tool_response": {}}),
            "event_type": "PostToolUse"}


@pytest.mark.parametrize("code", [
    "y = 1 if s >= 0.9 else 0", "y = 1 if (s >= 0.9) else 0", "y = 1 if model.score(x) >= 0.9 else 0",
    "y = 1 if s >= 0.9e-1 else 0", "y = int(p > 0.5)", "y = (p > 0.5).astype(int)",
    "    return 1 if s >= 0.9 else 0\n"])
def test_a_collapse_with_no_test_fires(code):
    assert gate([_row("src/score.py", code)]) is not None


@pytest.mark.parametrize("code", [
    'EXAMPLE = "1 if s >= 0.9 else 0"\n', "# y = 1 if s >= 0.9 else 0\n", "y = 1 if s >= 0.9 else 0.5",
    "y = int(s > 0.9 and s * 100)", "ok = True if vs_ver <= 12.0 else False", "y = a if s >= 0.9 else b"])
def test_what_is_not_a_collapse_is_silent(code):
    assert gate([_row("src/score.py", code)]) is None


@pytest.mark.parametrize("path, code", [
    ("tests/test_score.py", "assert f(0.89) == 0 and f(0.9) == 1\n"),
    ("C:\\repo\\tests\\test_score.py", "assert f(0.9) == 1\n"),
    ("app/tests.py", "assert f(0.9) == 1\n"),
    ("tests/test_score.py", "assert f(0.90) == 1\n")])
def test_a_test_carrying_the_threshold_pays(path, code):
    assert gate([_row("src/score.py", "y = 1 if s >= 0.9 else 0"), _row(path, code)]) is None


def test_scientific_notation_is_the_same_threshold():
    assert gate([_row("src/score.py", "y = 1 if s >= 0.9e-1 else 0"),
                 _row("tests/test_score.py", "assert f(0.9e-1) == 1")]) is None


def test_a_test_at_another_threshold_does_not_pay():
    assert gate([_row("src/score.py", "y = 1 if s >= 0.9 else 0"),
                 _row("tests/test_score.py", "assert f(0.5) == 1")]) is not None


def test_non_string_content_is_no_decision_not_a_crash():
    assert gate([_row("src/score.py", {"value": "t"})]) is None
    assert gate([_row("src/score.py", {"edits": [{"old_string": "a", "new_string": {"v": "t"}}]},
                      tool="MultiEdit")]) is None
