"""makoto.checks.unnamedFailure -- gate.unnamed_failure, register entry
`C12 VERDICT WITHOUT ITS SUBJECT`.

The turn counted a failure and never named the failing identity. The register states the fault as
*"a failure was counted but never named"* against the rule *"name the failing identity in its own
run"*. A count is a number the reader cannot act on: "3 failed" sends them back to the wall of
output the run already printed, and the one thing that would make the next step obvious -- WHICH
three -- was on the record and got dropped.

THE THIRD STATE IS THE POINT. This gate has three answers, not two:

  * the closing text carries no failure COUNT           -> nothing was counted, silent
  * a count, and the record holds no failing identity   -> NOT-EVALUABLE, silent
  * a count, the record holds failing identities, and   -> fires, naming one of them
    the text names none of them

The middle case is the one a two-valued check gets wrong. Makoto cannot invent an identity it
never recorded, and firing there would ask the agent to name something nobody has. `C2 MISSING
THIRD STATE` is itself a register entry, and this is its shape: an unevaluable cell is outside the
verdict's denominator, never a pass and never a fire.

COUNTED, not merely FAILED, and in PROSE. The predicate is this module's own
`_COUNTED_FAILURE_RX`, and that is a deliberate second lexicon with a measured reason rather than
an oversight. `vocab._FAILURE_SUMMARY_RX` is the shared one, and its every consumer is
OUTPUT-facing: `kit.is_failing_testrun` grades BLOCKING checks on it, so widening it is a change
to their verdicts. Its shape follows its subject -- a runner prints `3 failed`, adjacent. An
agent WRITES "3 tests failed", with the noun in between, and spells small numbers out. The two
subjects need different shapes, so they get one lexicon each; `substrate/claims.py` records the
same refusal for the same reason ("merging would change verdicts"). This one also drops the
`FAILURES!` banner and the bare `Traceback (most recent call last):` arms: something failed there
but nothing was COUNTED, and this entry is about a count whose subject went missing. Hedges that
name no number ("several failed", "a few failing") are out for the same reason -- the entry is
about a count, and admitting them widens it toward every hedge.

WHAT COUNTS AS NAMING IT. At least one BARE name of a currently-red recorded test must appear in
the text (`namedTestTeeth._TESTNAME_RX`, the one home for a test identity in prose; the recorded
ids are `path::name[param]`, so the comparison is on the bare function name, exactly as
`gate.named_test` does it). Naming some OTHER test does not discharge the count -- the rule is to
name the FAILING identity -- and that asymmetry is pinned by its own test.

Identities come from `namedTestTeeth.current_named_verdicts`, never from a second parser. That
function is also what keeps this gate sound: it reads per-test verdicts ONLY out of the response
of a recognized test-runner invocation, so a `FAILED` line the agent merely displayed with
`cat old.log` is not a run and cannot make this gate demand a name for it; and a red discharged
by a later recorded green of the same id is no longer red.

RECALL BOUNDS:
  * A failing identity named in prose without the `test_` prefix ("the parser test failed") is not
    seen, so the gate fires. The alternative is a similarity judgement between prose and an id,
    which is what `F12`'s row already declines for this tree.
  * Only test identities. A counted failure of something that is not a test -- a build step, a
    lint pass -- has no recorded identity vocabulary here, so it lands in the NOT-EVALUABLE arm.

DISCRIMINANT AGAINST `gate.named_test`, which reads the same substrate: that gate fires on a NAME
whose run went red, this one on a COUNT with no name at all. The two are exclusive by
construction -- a text with a name is not a text with no name -- and that is this gate's merge
witness.

ADVISORY TIER, NEVER BLOCK: the benign case is real and looks identical -- the agent pasted the
runner's own summary and the reader can see the names in it, or the count belongs to a run whose
per-test lines the 500-char recorded tail cut. No corpus-measured false-positive rate exists.
"""
from __future__ import annotations

from typing import Optional

import re

from makoto.kit import current_named_verdicts, unwitnessed
from makoto.vocab import Finding, _TESTNAME_RX

# SHAPE = OTHER_POINT: the witness is a second reading of the same subject -- the record's own
# currently-red test identities (`current_named_verdicts`, folded from history rows) -- compared
# against what the closing text itself names.
SHAPE = "OTHER_POINT"


# The bare function names of every currently-red recorded test identity -- the SAME
# `current_named_verdicts` fold `gate.named_test` reads, so a red discharged by a later recorded
# green of that id is no longer red here either. One-line by construction (module-level lambda,
# not `def`): the design pins this module's top-level function count at 1 (`unnamed_failure_gate`
# alone).
_red_names = lambda history: frozenset(
    tid.rpartition("::")[2].split("[", 1)[0]
    for tid, v in current_named_verdicts(history).items() if v == "FAIL")

# `ev` is `(text, history)`. The turn owes naming at least one of the record's own currently-red
# test identities, but ONLY once it has counted a failure at all -- a text with no counted
# failure, or a record with no red identity to name, owes nothing (the NOT-EVALUABLE third state
# the module docstring names).
owes = lambda ev: ((_red_names(ev[1]),)
                   if ev[0] and _COUNTED_FAILURE_RX.search(ev[0]) and _red_names(ev[1])
                   else ())
# No fresh event pays this obligation: the witness is the text's OWN content, checked once
# against the record in `paid` (see `unnamed_failure_gate`) -- naming even ONE of the red
# identities discharges the whole obligation, since this gate is about the habit of naming, not
# an exhaustive per-test tally.
pays = lambda _ev: None

# A COUNTED failure as an agent WRITES one. See the docstring for why this is not
# `vocab._FAILURE_SUMMARY_RX` and must not become it.
_COUNT = r"(?:[1-9]\d*|one|two|three|four|five|six|seven|eight|nine|ten)"
_SUBJECT = r"(?:tests?|checks?|cases?|specs?|suites?|assertions?|examples?)"
_VERDICT = r"(?:failed|failures?|failing|errors?|erroring)"
_COUNTED_FAILURE_RX = re.compile(
    rf"\b{_COUNT}\s+(?:{_SUBJECT}\s+)?{_VERDICT}\b"
    rf"|\b(?:failures?|errors?)\s*:\s*[1-9]\d*\b",
    re.IGNORECASE)


def unnamed_failure_gate(text, *, history=()) -> Optional[Finding]:
    """Fire iff the closing text counts at least one failure, the record holds at least one
    currently-red test identity, and the text names none of them."""
    for _ev, _red_names in unwitnessed(
            ((text, history),), owes=owes, pays=pays,
            paid=(lambda names: bool(names & set(_TESTNAME_RX.findall(text))),)):
        verdict = current_named_verdicts(history)
        red = sorted(tid for tid, v in verdict.items() if v == "FAIL")
        return Finding(
            pattern_id="gate.unnamed_failure",
            file="tests",
            line=0,
            level="advisory",
            message=(
                f"the turn counts a failure and names none of the {len(red)} failing test "
                f"identit{'y' if len(red) == 1 else 'ies'} the run itself recorded (e.g. {red[0]}). "
                f"A count sends the reader back to the output; the name is the thing they act on."
            ),
            retry_hint=(
                "Name the failing identities in the same turn that counts them -- the recorded ids "
                "are already on the record, so this is a copy, not a re-run."
            ),
            snippet=red[0][:200],
        )
    return None


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unnamed_failure", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="TESTRUN_DELTA",
               eats=frozenset({"text", "history"}),
               run=lambda c: unnamed_failure_gate(c.text, history=c.history))
