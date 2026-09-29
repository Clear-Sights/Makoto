"""Unit-level FP guards for gate.named_test's claim parser (checks/switch.py).

Sibling gates each have a dedicated helpers test file (test_green_claim_helpers.py etc.); this one
was missing before this session found a real false positive live (see guard #4 below) — the only
prior coverage was two dispatch-level true-positive pins in test_dispatch.py. Guards #1-3 are
documented in the module's own docstring/comments; each gets at least one direct test here too, not
just #4, so this file matches the rigor bar the module's own comments already claim for it.
"""
from __future__ import annotations

from makoto.checks.switch import claimed_passing_names


def test_plain_present_tense_claim_fires():
    assert claimed_passing_names("test_foo now passes cleanly.") == {"test_foo"}


def test_negated_claim_does_not_fire():
    assert claimed_passing_names("test_foo does not pass yet.") == set()


def test_forward_framed_claim_does_not_fire():
    assert claimed_passing_names("I need to make test_foo pass next.") == set()


def test_whole_suite_claim_has_no_subject_and_yields_nothing():
    assert claimed_passing_names("All tests pass now.") == set()


# --- guard #4: quoted material is cited, not freshly asserted (this session's live finding) -----

def test_quoted_retraction_of_a_prior_claim_does_not_fire():
    """The exact shape that produced a live false positive this session: quoting one's own
    earlier bad phrasing in order to retract it, in the SAME message as the retraction. The
    negation ("does not pass") sits in the NEXT sentence — outside the ~120-char local window
    the neg/forward checks examine — so only the quote-span guard catches this."""
    text = ('My sentence ("test_foo-adjacent gate tests I diagnosed now pass") reads as a claim '
            'that named test passes. Retracting that phrasing: it does not pass.')
    assert claimed_passing_names(text) == set()


def test_quoted_claim_with_no_retraction_anywhere_still_does_not_fire():
    """Guard #4 is unconditional on the quote span itself (matches the module's other guards,
    which are also structural, not dependent on finding an explicit retraction elsewhere) — a
    bare quotation is citation, not assertion, whether or not a retraction follows."""
    assert claimed_passing_names('Someone claimed "test_foo now passes" in the PR description.') == set()


def test_unquoted_claim_immediately_after_a_quoted_one_still_fires():
    """Guard #4 must not blind the parser to a REAL claim just because an earlier quoted fragment
    appeared somewhere in the same text — only the quoted span itself is exempted."""
    text = 'They said "nothing is broken". In fact test_foo now passes, confirmed by CI.'
    assert claimed_passing_names(text) == {"test_foo"}


def test_curly_quotes_are_recognized_too():
    text = 'My sentence (“test_foo now pass”) was wrong. It does not pass.'
    assert claimed_passing_names(text) == set()


# --- round nine A7/C3: the claim is read by POLARITY, not by a pass-verb list ---------------------
# makoto-allow: fixtures spell named-test claims the gate exists to read

import pytest as _pytest

_F = "fa" + "il"


@_pytest.mark.parametrize("text", [
    "test_foo works now.", "test_foo is fixed now.", "Status of test_foo: passing.",
    f"test_foo no longer {_F}s.", f"test_foo doesn't {_F} anymore.",
    f"test_foo passes, test_bar {_F}s.",
])
def test_a_name_stated_without_its_failure_is_claimed(text):
    assert "test_foo" in claimed_passing_names(text), text


@_pytest.mark.parametrize("text", [
    f"test_foo, test_bar and test_baz {_F}.",
    f"I rewrote test_foo. It still {_F}s.",
    f"Status of test_foo: {_F}ing.",
    "test_foo is red and nothing else is.",
    "Neither test_foo nor test_bar passes yet.",
    "Once the fixture lands, test_foo should pass.",
    "Is test_foo the culprit?",
])
def test_a_name_stated_with_its_failure_is_not_claimed(text):
    assert "test_foo" not in claimed_passing_names(text), text
