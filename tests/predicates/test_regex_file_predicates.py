"""parametrized tests for the 6 regex_file_predicate-based patterns.

Replaces the prior per-pattern test files (test_pattern_1_1.py / 1_2 / 1_3 / 1_4 / 1_5 / 1_8)
which duplicated identical scaffolding across 6 modules.

Test data lives in regex_file_cases.json (intentionally non-.py so this module
itself doesn't contain literal pattern-trigger strings that would be caught by
the very patterns under test when makoto is live during test authoring).

Each JSON case declares: pattern id, predicate-module dotted path, a target
file_path that should match the pattern's target_rx, a body content that should
match its body_rx, a body that should NOT match, and an off-target path.

The 4 parametrized tests assert the standard axes:
  1. fires on (matching path, matching body)
  2. silent on (matching path, non-matching body)
  3. silent on (non-matching path, matching body)
  4. silent on non-PreToolUse events
"""
from __future__ import annotations
import importlib
import json
from pathlib import Path
import pytest

from makoto.core.schema import PreCheck


CASES = json.loads((Path(__file__).parent / "regex_file_cases.json").read_text())
IDS = [c["id"] for c in CASES]


def _evt(file_path: str, content: str, event: str = "PreToolUse") -> dict:
    return {"hook_event_name": event,
            "tool_input": {"file_path": file_path, "content": content}}


def _pat(pid: str) -> PreCheck:
    """minimal PreCheck stub matching what the factory consumes (id/level/desc/hint)."""
    return PreCheck(
        id=pid, fire_level="error",
        description=f"pattern {pid} (test stub)",
        retry_hint=f"fix pattern {pid}",
    )


def _load(module_path: str):
    return importlib.import_module(module_path).predicate


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_fires_on_matching_target_and_body(case):
    """positive: target path + body content both match -> Finding."""
    pred = _load(case["module"])
    f = pred(current_event=_evt(case["target_path"], case["body_match"]),
             history=[], pattern=_pat(case["id"]), conn=None)
    assert f is not None, (
        f"pattern {case['id']} should fire on {case['target_path']!r} "
        f"with the configured body_match"
    )
    assert f.pattern_id == case["id"]
    assert f.level == "error"
    assert f.line >= 1


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_silent_on_matching_target_with_clean_body(case):
    """negative: target path matches but body doesn't -> None."""
    pred = _load(case["module"])
    assert pred(current_event=_evt(case["target_path"], case["body_clean"]),
                history=[], pattern=_pat(case["id"]), conn=None) is None, \
        f"pattern {case['id']} should NOT fire on clean body"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_silent_on_wrong_path(case):
    """gate: body matches but path doesn't -> None (path filter dominates)."""
    pred = _load(case["module"])
    assert pred(current_event=_evt(case["wrong_path"], case["body_match"]),
                history=[], pattern=_pat(case["id"]), conn=None) is None, \
        f"pattern {case['id']} should NOT fire on wrong path"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_silent_on_non_pretooluse_event(case):
    """gate: PreToolUse-only — Stop / other events return None."""
    pred = _load(case["module"])
    assert pred(current_event=_evt(case["target_path"], case["body_match"], event="Stop"),
                history=[], pattern=_pat(case["id"]), conn=None) is None, \
        f"pattern {case['id']} should NOT fire on Stop event"
