"""makoto.checks.reportBeforeRun -- gate.report_before_run, register entry
`C11 REPORT BEFORE DECIDE`.

A run's verdict was written into a prose document before any verifier had run in this session.
The register states the fault as *"the outcome was emitted after the narration about it"* against
the rule *"emit the outcome first; reporting comes after"*. A report that precedes the outcome it
reports cannot be a reading of it: whatever it says was decided before there was anything to
decide from, so the words are a prediction wearing a result's grammar.

WHAT ORDER IS READ. `kit.unmet_obligation_gate`, the same factory the seven Keel-shaped
obligations use, so the ordering rule keeps ONE home -- the order IS the check. The act is a
settled mutation of a prose document whose introduced text states a run verdict; the guard is
`kit.ran_a_verifier`. The gate fires when the act lands with no verifier run anywhere before it.

PROSE DOCUMENTS ONLY, and this is the measurement that makes the check material. A run verdict
inside a `.py` file is a FIXTURE or an expected-output string, not a report -- this package's own
tests carry `2 failed, 56 passed in 2.0s` as test data, and a gate that fired on writing them
would fire on writing itself. `checks/integritySuppressionFlag.py` records the mirror-image
decision for the mirror-image reason: it dropped `.md` because markdown QUOTES examples where its
subject is live config. Here markdown is exactly the subject, because a narration lives in prose,
and code is exactly the exclusion, because a verdict in code is data.

WHY A WHOLE-SESSION GUARD RATHER THAN A PER-DOCUMENT ONE. The guard is "any verifier ran at all
before this write", not "a verifier ran for the thing this document describes". Pairing a document
to its subject is the prose-to-referent judgement `F12`'s row declines for this tree. The loose
guard costs recall and buys soundness: a session that ran something and then wrote a verdict about
something else is silent here. What it still catches is the shape that has no innocent reading --
a verdict written into prose in a session where nothing was ever run.

The benign case it does admit: DOCUMENTING a command's output ("the suite prints `58 passed`") in
a session that never ran it. Real, and narrower than it sounds -- an agent documenting output
almost always ran the command first, and the first run in the session discharges the obligation
for every later write.

DISCRIMINANT AGAINST `gate.green_claim`, which grades the same vocabulary: that gate reads the
assistant's CLOSING TEXT and asks whether a green claim has a green run behind it; this one reads
INTRODUCED FILE CONTENT in history ORDER and asks whether any run preceded it. A session whose
only act is writing "all tests pass" into a document, with empty closing text, fires this gate and
gives green_claim nothing to key on. That is this gate's merge witness.

ADVISORY TIER, NEVER BLOCK: the documenting case above is real and looks identical, and no
corpus-measured false-positive rate exists.
"""
from __future__ import annotations

import re

from makoto.kit import introduced_text, ran_a_verifier, unmet_obligation_gate
from makoto.substrate.claims import whole_suite_pass_claim
from makoto.vocab import _SUCCESS_SUMMARY_RX

# A PROSE document -- where a narration lives. Code is excluded by extension, deliberately; see
# the docstring's measurement.
_PROSE_TARGET_RX = re.compile(r"\.(?:md|markdown|rst|txt|adoc|org)$", re.IGNORECASE)
_MUTATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})


def _reports_a_run_verdict(ev: dict) -> bool:
    """This settled event wrote a run's verdict into a prose document.

    Two readers, both already in the tree and neither copied: `vocab._SUCCESS_SUMMARY_RX` for a
    PASTED runner summary ("58 passed"), and `substrate/claims.whole_suite_pass_claim` for the
    same verdict written as PROSE ("the suite is green"). The second is the tree's FP-hardened
    claim reader -- it firewalls a subset claim from a whole-suite one, and refuses a negated,
    forward-framed, or code-quoted match -- and gate.green_claim grades the closing text on that
    same object. A third copy of either is what `F2 TWO SOURCES OF TRUTH` names.

    THE GREEN DIRECTION ONLY, named rather than implied. A prose failure count written before
    anything ran ("3 tests failed") is the same ORDER fault, and this gate does not see it: the
    shared summary lexicon is output-shaped and wants the count adjacent (`3 failed`), and the
    prose-shaped one belongs to gate.unnamed_failure, in whose own subject it was measured --
    copying it here is the duplication above. The asymmetry also costs least where it matters:
    a report of success written before the run is the half that MISLEADS, and it is the half
    with a hardened reader.
    """
    if ev.get("hook_event_name") != "PostToolUse":
        return False                       # a call that may never have landed wrote nothing
    tool = ev.get("tool_name", "")
    if tool not in _MUTATION_TOOLS:
        return False
    ti = ev.get("tool_input", {}) or {}
    if not isinstance(ti, dict) or not _PROSE_TARGET_RX.search(str(ti.get("file_path", ""))):
        return False
    text = introduced_text(tool, ti)
    return bool(text) and bool(_SUCCESS_SUMMARY_RX.search(text)
                               or whole_suite_pass_claim(text))


report_before_run_gate = unmet_obligation_gate(
    act=_reports_a_run_verdict,
    guard=ran_a_verifier,
    pattern_id="gate.report_before_run",
    message=("a run's success was written into a prose document with no verifier run anywhere "
             "before it — the report precedes the outcome it reports, so it is a prediction in a "
             "result's grammar."),
    retry_hint=("Run the verifier first and write the verdict from what it printed; or, if the "
                "document is quoting an example rather than reporting this session's run, say so "
                "in the document."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.report_before_run", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: report_before_run_gate(c.history))
