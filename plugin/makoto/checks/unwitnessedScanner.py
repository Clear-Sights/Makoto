"""makoto.checks.unwitnessedScanner -- gate.unwitnessed_verifier, register entry
`B4 WRONG ORACLE`.

A verifier reported clean and this session has never seen that verifier report a failure. A
clean report from an oracle never observed failing is not evidence of absence; it is evidence of
nothing, because a verifier that cannot fire and a subject that is genuinely clean print the same
word. Keel states the same point as clause U25 (`clear-sights/keel`,
`plugin/keel/clauses.json`): *"a scan reported clean and this session has not seen a scanner
report findings; run its prefix-distractor regression before the next act."*

WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS A DIFFERENT QUESTION. The row read
"proxy-versus-target disagreement is a similarity judgement over two oracles", which is true of
deciding whether the verifier MEASURES the thing you care about. This gate asks the weaker,
countable question: has it been seen to fire at all. That is `B1 CHECKER SELF-TRUST`'s own demand
-- *see the verdict flip on a plant first* -- turned on a verifier the agent is about to trust,
and it is entirely on the record makoto reads: the command, and what it printed.

THE VOCABULARY IS EXACTLY `vocab._TEST_RUNNER_RX`, SHARED AND UNCHANGED, and that is a scope
statement rather than a convenience. `_TEST_RUNNER_RX` is the catalog's one home for "a
command that runs a verifier and prints a report", and it is a TEST-runner list: pytest, jest,
go test, cargo test, npm test and their siblings. A linter or security scanner (`ruff`, `mypy`,
`eslint`, `semgrep`) is NOT in it, so this gate does not see one. That is a named RECALL bound
and it fails quiet. It is deliberately not fixed by adding a second vocabulary: two lists of
"what a verifier is" is `F2 TWO SOURCES OF TRUTH`, and a longer closed list misses the next
unlisted tool identically. Widening belongs in `_TEST_RUNNER_RX` itself, once, if it is ever
worth it.

ADVISORY TIER, NEVER BLOCK: a first clean run in a fresh session is the overwhelmingly common
benign case -- most sessions never see a red run and should not -- and no corpus-measured
false-positive rate exists for the distinction.
"""
from __future__ import annotations

import re

from makoto.vocab import Finding, _TEST_RUNNER_RX
from makoto.kit import unmet_obligation_gate, response_text, command_of

# A report with NO failures: a non-zero passed count, or an explicit all-clear. Narrow and
# lexical on purpose -- the words a runner prints, not an interpretation of them.
_CLEAN_REPORT_RX = re.compile(
    r"\b[1-9]\d*\s+passed\b|\ball\s+(?:tests?|checks?|specs?)\s+passed\b|\bOK\b|\bPASS(?:ED)?\b",
    re.I)
# A report WITH failures -- the witness that this verifier can fire.
#
# NOT case-insensitive as a whole, and the reason is a bug this regex had for one draft:
# `re.I` over `\bFAILED\b` matches the WORD "failed", so "58 passed, 0 failed" read as a
# verifier firing and the gate went quiet on exactly the report it exists for. The counted form
# is case-insensitive and anchored to a NON-ZERO count (`[1-9]`); the bare report tokens are
# case-SENSITIVE, because `FAILED`/`FAIL` in capitals are what a runner prints as a verdict
# while "failed" in prose is not.
_FAILING_REPORT_RX = re.compile(
    r"(?i:\b[1-9]\d*\s+(?:failed|failures?|errors?)\b)|\bFAILED\b|\bFAIL\b"
    r"|\bAssertionError\b")


def _is_clean_verifier_run(ev: dict) -> bool:
    cmd = command_of(ev)
    if not cmd or not _TEST_RUNNER_RX.search(cmd):
        return False
    out = response_text(ev)
    # A report cannot be both, and failures win: "1 failed, 40 passed" is the verifier firing.
    return bool(out and _CLEAN_REPORT_RX.search(out) and not _FAILING_REPORT_RX.search(out))


def _is_failing_verifier_run(ev: dict) -> bool:
    cmd = command_of(ev)
    if not cmd or not _TEST_RUNNER_RX.search(cmd):
        return False
    return bool(_FAILING_REPORT_RX.search(response_text(ev)))


unwitnessed_verifier_gate = unmet_obligation_gate(
    act=_is_clean_verifier_run,
    guard=_is_failing_verifier_run,
    pattern_id="gate.unwitnessed_verifier",
    message=("A verifier reported clean and this session has never seen it report a failure — a "
             "verifier that cannot fire and a genuinely clean subject print the same word, so "
             "the clean report is evidence of nothing on its own."),
    retry_hint=("Plant a fault the verifier must catch and see it fail, or cite an earlier red "
                "run of the same verifier; then the clean report carries weight."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unwitnessed_verifier", applies_at="Stop", posture="ADVISE", may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: unwitnessed_verifier_gate(c.history))
