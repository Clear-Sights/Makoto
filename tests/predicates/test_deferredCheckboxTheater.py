"""tests for pattern 1.5 — DEFERRED checkbox theater on docs/pristine-baseline.md.

Narrowly scoped (target = the single file docs/pristine-baseline.md), so no general-content FP.
TP: a checked DEFERRED box on that file. TN: the same on a different file (wrong path), an
UNCHECKED DEFERRED box (legit open item), a checked DONE box, and a non-PreToolUse event.
"""
from makoto.checks.deferredCheckboxTheater import predicate
from makoto.core.schema import PreCheck

_PAT = PreCheck(id="content.deferred_checkbox_theater", fire_level="error", description="DEFERRED checkbox theater", retry_hint="x")


def _evt(file_path: str, content: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_input": {"file_path": file_path, "content": content}}


def test_fires_on_checked_deferred_uppercase():
    f = predicate(current_event=_evt("docs/pristine-baseline.md", "- [x] DEFERRED T-12 audit wiring\n"),
                  history=[], pattern=_PAT)
    assert f is not None and f.pattern_id == "content.deferred_checkbox_theater"


def test_fires_on_checked_deferred_lowercase():
    assert predicate(current_event=_evt("repo/docs/pristine-baseline.md", "- [x] deferred to next cycle\n"),
                     history=[], pattern=_PAT) is not None


def test_silent_on_wrong_file():
    # same theater shape but NOT the baseline scorecard -> narrow target means no fire
    assert predicate(current_event=_evt("docs/notes.md", "- [x] DEFERRED something\n"),
                     history=[], pattern=_PAT) is None


def test_silent_on_unchecked_deferred():
    # an open (unchecked) deferred item is legit, not theater
    assert predicate(current_event=_evt("docs/pristine-baseline.md", "- [ ] DEFERRED T-12\n"),
                     history=[], pattern=_PAT) is None


def test_silent_on_checked_done():
    assert predicate(current_event=_evt("docs/pristine-baseline.md", "- [x] DONE T-12\n"),
                     history=[], pattern=_PAT) is None


def test_silent_on_non_pretooluse():
    assert predicate(current_event={"hook_event_name": "Stop",
                                    "tool_input": {"file_path": "docs/pristine-baseline.md", "content": "- [x] DEFERRED T-1\n"}},
                     history=[], pattern=_PAT) is None
