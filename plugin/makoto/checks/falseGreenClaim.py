from __future__ import annotations
from typing import Optional
from makoto.vocab import Finding
from makoto.kit import is_failing_testrun
from makoto.substrate.claims import whole_suite_pass_claim


# The prose half (the whole-suite green-claim signal) lives in substrate.claims.whole_suite_pass_claim,
# shared with gate.stale_pass (which additionally uses the returned Match's POSITION for its teeth
# window). See docs/adr/0032-green-claim-signal-relocation.md for the relocation history.
def green_claim_gate(text, *, testrun_output, testrun_exit=None) -> Optional[Finding]:
    """Fire iff the assistant claims UNIVERSAL test success ('tests pass', 'the suite is green',
    'CI is green') while the MOST RECENT recorded test-runner output shows a REAL failure — a
    verifiable contradiction between "the tests pass" and the last run the world actually recorded.

    Two conjuncts, both required (so an honest re-run-to-green, a subset claim, or a no-test turn
    is silent):
      1. `whole_suite_pass_claim(text)` — a whole-suite green claim (subset / negated / forward /
         code-quoted claims are inert), AND
      2. `testrun_output` (the latest kind='testrun' ledger row, passed in by run_stop_checks) is a
         FAILING run per `is_failing_testrun` — xfail-safe and 0-failed-safe, so an
         expected-fail run ('=== 681 passed, 3 xfailed ===') or a clean run does NOT fire.
    Silent when: no green claim, no test runner ran (empty output), or the latest recorded run
    carries no RECOGNIZED failure token. That last case is BROADER than 'the latest run passed':
    `is_failing_testrun` detects the PRESENCE of failure, never the presence of success, so a run
    that really was red but whose recorded 500-char output tail holds no failure token (a
    timeout/'Killed' tail, a bare 'ERROR:' collection abort, a coverage/warnings footer that pushed
    the summary out of the tail) is silent here — and the ledger `exit` column recorded on that same
    row is never consulted. This is the gate's known absence-reads-as-green edge, stated, not
    inferred. The 'most recent' ordering means a fix-and-rerun-green supersedes an earlier red and
    never fires; it is also SCOPE-BLIND — a narrow green re-run supersedes a whole-suite red."""
    if not whole_suite_pass_claim(text):
        return None                                  # no whole-suite green claim -> inert
    # THE STATUS FIRST, the tail second. A nonzero exit on the latest recorded testrun is the run
    # saying it failed, in a number: it carries no vocabulary, cannot be paraphrased, and does not
    # depend on a 500-char tail having kept the summary line. This is the half of the
    # absence-reads-as-green edge that CAN be closed, and it is closed positively rather than by
    # widening the token list -- a longer token list has the identical silent mode waiting for the
    # next runner whose failure it does not spell.
    if testrun_exit is not None and testrun_exit != 0:
        return _finding()
    if not testrun_output or not is_failing_testrun(testrun_output):
        return None                                  # no run, or the latest run was green/xfail
    return _finding()


def _finding() -> Finding:
    """One construction, reached by both signals, so the two cannot drift into two messages."""
    return Finding(
        pattern_id="gate.green_claim",
        file="tests",
        line=0,
        level="error",
        message=("Claim states the tests/suite pass, but the most recent recorded test run shows "
                 "a failure — re-run the suite to green and cite it, or scope/retract the claim."),
        retry_hint="Re-run the suite to green and cite it, or narrow the claim to what actually passed.",
    )


from makoto.registry import Check as _Check
# tests="": registered ONE_OFF -- claim-vs-history and test-run-delta genuinely straddle here.
CHECK = _Check(id="gate.green_claim", applies_at="Stop", posture="BLOCK", may_block=True,
               eats=frozenset({"text", "testrun_output", "testrun_exit"}),
               run=lambda c: green_claim_gate(c.text, testrun_output=c.testrun_output,
                                             testrun_exit=c.testrun_exit))
