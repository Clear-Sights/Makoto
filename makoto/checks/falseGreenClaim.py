from __future__ import annotations
from typing import Optional
from makoto.core.schema import Finding
from makoto.substrate.io import is_failing_testrun
from makoto.substrate.claims import whole_suite_pass_claim


# The prose half (the whole-suite green-claim signal) RELOCATED to substrate.claims.whole_suite_pass_claim
# (consolidation T2.2, 2026-06-09): truthiness-identical pure relocation; the second consumer is
# gate.stale_pass, which additionally uses the returned Match's POSITION for its teeth window.
def green_claim_gate(text, *, testrun_output) -> Optional[Finding]:
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
    Silent when: no green claim, no test runner ran (empty output), or the latest run passed. The
    'most recent' ordering means a fix-and-rerun-green supersedes an earlier red and never fires."""
    if not whole_suite_pass_claim(text):
        return None                                  # no whole-suite green claim -> inert
    if not testrun_output or not is_failing_testrun(testrun_output):
        return None                                  # no run, or the latest run was green/xfail
    return Finding(
        pattern_id="gate.green_claim",
        file="tests",
        line=0,
        level="error",
        message=("Claim states the tests/suite pass, but the most recent recorded test run shows "
                 "a failure — re-run the suite to green and cite it, or scope/retract the claim."),
        retry_hint="Re-run the suite to green and cite it, or narrow the claim to what actually passed.",
    )


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.green_claim", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: green_claim_gate(c.text, testrun_output=c.testrun_output))
