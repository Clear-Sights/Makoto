"""parametrized tests for the content-scan patterns cased in regex_file_cases.json.

Replaces the prior per-pattern test files (test_pattern_1_1.py / 1_2 / 1_3 / 1_4 / 1_5 / 1_8)
which duplicated identical scaffolding across 6 modules; 1.2/1.3/1.8 were CUT 2026-06-02
(warning-tier elimination), so the case set holds the 3 survivors. Each case id must name a
LIVE `load_precheck_catalog()` entry whose predicate_module matches the case -- a dead or
renamed id fails loudly instead of being echoed back to itself by a self-built stub.

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

from makoto.vocab import PreCheck
from makoto.registry import load_precheck_catalog


CASES = json.loads((Path(__file__).parent / "regex_file_cases.json").read_text())
# Silent-thinning guard (mirrors test_corpus_content_scan._params' own): an EMPTY case set must
# be a loud collection failure, not "4 skipped, exit 0" -- a fully green run in which none of
# the cased patterns is exercised is the exact shipped bug class this battery exists to catch.
assert CASES, "regex_file_cases.json resolved ZERO cases -- the battery would read green while exercising nothing"
IDS = [c["id"] for c in CASES]


def _evt(file_path: str, content: str, event: str = "PreToolUse") -> dict:
    return {"hook_event_name": event,
            "tool_input": {"file_path": file_path, "content": content}}


def _pat(pid: str) -> PreCheck:
    """The LIVE catalog entry for `pid`. The prior self-built stub echoed whatever id the JSON
    held straight through kit._exempt_or_finding, so `f.pattern_id == case["id"]` was a
    tautology over ids (1.1/1.4/1.5) the catalog had long since renamed -- resolving here makes
    a dead case id an immediate loud failure."""
    matches = [p for p in load_precheck_catalog() if p.id == pid]
    assert matches, f"case id {pid!r} is not in the live precheck catalog"
    return matches[0]


def _load(module_path: str):
    return importlib.import_module(module_path).predicate


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_fires_on_matching_target_and_body(case):
    """positive: target path + body content both match -> Finding."""
    pred = _load(case["module"])
    pat = _pat(case["id"])
    assert pat.predicate_module == case["module"], (
        f"case {case['id']!r} names module {case['module']!r} but the live catalog wires "
        f"{pat.predicate_module!r} -- the battery would exercise a module the check no longer uses"
    )
    f = pred(current_event=_evt(case["target_path"], case["body_match"]),
             history=[], pattern=pat, conn=None)
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
