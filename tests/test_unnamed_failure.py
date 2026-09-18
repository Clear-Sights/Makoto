"""gate.unnamed_failure (register C12 VERDICT WITHOUT ITS SUBJECT) -- the three states.

The gate is three-valued and the middle state is what a two-valued check gets wrong, so the
tests are organised by state: no count, a count with no identity on the record (NOT-EVALUABLE),
and a count whose recorded identity the turn dropped (fires). The fourth group pins the
asymmetry the register's own rule creates -- naming some OTHER test does not discharge a count,
because the rule is to name the FAILING identity.
"""
from __future__ import annotations

import pytest

from makoto.checks.unnamedFailure import (
    CHECK, _COUNTED_FAILURE_RX, unnamed_failure_gate,
)

RED_OUTPUT = ("tests/test_billing.py::test_charge FAILED\n"
              "tests/test_billing.py::test_refund FAILED\n"
              "2 failed, 56 passed in 2.0s")


def _run_row(command, stdout):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": command},
                        "tool_response": {"stdout": stdout, "exitCode": 1}}}


def _red_history():
    return [_run_row("python3 -m pytest -q", RED_OUTPUT)]


# ---- state 1: nothing was counted ------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "All good.",
    "The suite is green.",
    "0 failed.",
    "58 passed in 2.0s",
    "several tests failed",          # a hedge names no count
    "a few failing",                 # same
    "5 minutes after the deploy failed",   # a count that is not a count OF failures
])
def test_silent_when_nothing_was_counted(text):
    assert unnamed_failure_gate(text, history=_red_history()) is None


@pytest.mark.parametrize("text", [
    "2 failed.", "3 tests failed; fixing now.", "Three tests failed.",
    "1 test failing.", "2 errors.", "Failures: 2", "four checks failing",
])
def test_the_prose_counts_that_do_count(text):
    """The lexicon's positive side, so it cannot go dead without this reddening. `N tests failed`
    with the noun in between is the form an agent writes and the form the shared OUTPUT lexicon
    (`vocab._FAILURE_SUMMARY_RX`, which a runner's adjacent `N failed` fits) does not carry."""
    assert _COUNTED_FAILURE_RX.search(text), text


def test_the_shared_output_lexicon_is_not_this_one_and_must_not_become_it():
    """The divergence is deliberate and measured, so it is pinned rather than left to drift. The
    shared one grades BLOCKING checks through kit.is_failing_testrun, so widening it changes their
    verdicts; this one is prose-shaped and narrower on the arms that count nothing."""
    from makoto.vocab import _FAILURE_SUMMARY_RX
    assert _FAILURE_SUMMARY_RX.search("Traceback (most recent call last):")
    assert not _COUNTED_FAILURE_RX.search("Traceback (most recent call last):")
    assert _FAILURE_SUMMARY_RX.search("FAILURES!")
    assert not _COUNTED_FAILURE_RX.search("FAILURES!")
    assert _COUNTED_FAILURE_RX.search("3 tests failed")
    assert not _FAILURE_SUMMARY_RX.search("3 tests failed")


def test_the_gate_itself_is_silent_on_an_uncounted_traceback():
    """Not just the two regexes side by side: the GATE must be reading the narrow one. A plant
    that swaps in the shared output lexicon leaves the comparison above green and reddens here."""
    text = "The run blew up:\nTraceback (most recent call last):\n  File \"x.py\", line 1"
    assert unnamed_failure_gate(text, history=_red_history()) is None


# ---- state 2: NOT-EVALUABLE -- a count with no identity on the record -------------------------

def test_not_evaluable_when_the_record_holds_no_failing_identity():
    """The third state. Makoto cannot ask for a name nobody has, so an unevaluable cell is
    outside the verdict's denominator -- never a pass, and never a fire either."""
    assert unnamed_failure_gate("2 failed.", history=[]) is None


def test_not_evaluable_when_the_failed_line_was_only_DISPLAYED():
    """`cat old.log` is not a run. The soundness this rests on lives in
    namedTestTeeth.current_named_verdicts, and it is load-bearing here: without it the gate would
    demand a name for a failure that never happened this session."""
    history = [_run_row("cat old.log", "tests/test_billing.py::test_charge FAILED")]
    assert unnamed_failure_gate("2 failed.", history=history) is None


def test_not_evaluable_once_a_later_green_run_discharges_the_red():
    """Last verdict wins, from the same substrate: a fixed-and-rerun test is no longer red, so
    there is no identity left to name."""
    history = _red_history() + [_run_row(
        "python3 -m pytest -q",
        "tests/test_billing.py::test_charge PASSED\n"
        "tests/test_billing.py::test_refund PASSED\n58 passed in 2.0s")]
    assert unnamed_failure_gate("2 failed, now fixed.", history=history) is None


# ---- state 3: the count's subject went missing -----------------------------------------------

def test_fires_on_a_count_with_no_name():
    """The scenario tests/test_stop_gate_level_invariant.py names for this gate."""
    finding = unnamed_failure_gate("2 tests failed; looking into it.", history=_red_history())
    assert finding is not None
    assert finding.pattern_id == "gate.unnamed_failure"
    assert finding.level == "advisory"
    assert "test_charge" in finding.message, "the finding must name the identity that was dropped"


def test_silent_once_a_failing_identity_is_named():
    assert unnamed_failure_gate("2 failed: test_charge and test_refund.",
                                history=_red_history()) is None


def test_naming_ONE_of_several_failing_identities_discharges_the_count():
    """The rule is to name the failing identity, not to enumerate every one. A turn that names
    one of two has stopped sending the reader back to the output, which is the fault."""
    assert unnamed_failure_gate("2 failed, test_charge among them.",
                                history=_red_history()) is None


def test_naming_some_OTHER_test_does_not_discharge_the_count():
    """The asymmetry the register's rule creates, and the reason the comparison is against the
    RED names rather than against any test name at all."""
    finding = unnamed_failure_gate("2 failed, but test_unrelated passes.", history=_red_history())
    assert finding is not None


def test_a_parametrized_id_is_matched_on_its_bare_name():
    """Recorded ids are `path::name[param]`; prose names the bare function. Same grain
    gate.named_test uses, and not a second way of comparing the two."""
    history = [_run_row("python3 -m pytest -q",
                        "tests/test_billing.py::test_charge[eur] FAILED\n1 failed in 1.0s")]
    assert unnamed_failure_gate("1 failed: test_charge.", history=history) is None
    assert unnamed_failure_gate("1 test failed.", history=history) is not None


def test_an_undecodable_history_row_is_no_recorded_verdict():
    assert unnamed_failure_gate("2 failed.", history=[object(), None, "not a row"]) is None


def test_the_check_ships_advisory_and_declares_its_shape():
    assert CHECK.posture == "ADVISE"
    assert CHECK.applies_at == "Stop"
    assert CHECK.tests == "TESTRUN_DELTA"
    assert CHECK.eats == frozenset({"text", "history"})
