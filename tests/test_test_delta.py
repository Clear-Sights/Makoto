"""Tests for makoto.checks.testDelta.compute_delta -- Task 3's test-delta redirect."""
from __future__ import annotations

from makoto.substrate._testDelta import compute_delta


def test_none_when_no_prior_output():
    assert compute_delta("", "FAILED tests/x.py::test_a\n") is None
    assert compute_delta(None, "FAILED tests/x.py::test_a\n") is None


def test_none_when_no_new_output():
    assert compute_delta("PASSED tests/x.py::test_a\n", "") is None


def test_none_when_verdict_set_is_unchanged():
    prior = "FAILED tests/x.py::test_a\nPASSED tests/x.py::test_b\n"
    same = "FAILED tests/x.py::test_a\nPASSED tests/x.py::test_b\n"
    assert compute_delta(prior, same) is None


def test_newly_failing_reported():
    prior = "PASSED tests/x.py::test_a\n"
    new = "FAILED tests/x.py::test_a\n"
    delta = compute_delta(prior, new)
    assert delta is not None
    assert "1 newly failing: test_a" in delta


def test_newly_passing_reported():
    prior = "FAILED tests/x.py::test_a\n"
    new = "PASSED tests/x.py::test_a\n"
    delta = compute_delta(prior, new)
    assert delta is not None
    assert "1 newly passing: test_a" in delta


def test_still_failing_test_is_not_in_the_delta():
    """A test that was failing before and is STILL failing is not new information -- must not
    appear in the delta (grounds on what CHANGED, never the whole persistent state)."""
    prior = "FAILED tests/x.py::test_a\n"
    new = "FAILED tests/x.py::test_a\nFAILED tests/x.py::test_b\n"
    delta = compute_delta(prior, new)
    assert delta == "1 newly failing: test_b"


def test_both_newly_failing_and_newly_passing_in_one_delta():
    prior = "FAILED tests/x.py::test_a\nPASSED tests/x.py::test_b\n"
    new = "PASSED tests/x.py::test_a\nFAILED tests/x.py::test_b\n"
    delta = compute_delta(prior, new)
    assert "1 newly passing: test_a" in delta
    assert "1 newly failing: test_b" in delta
