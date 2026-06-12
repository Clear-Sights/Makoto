from __future__ import annotations
import re
from typing import Optional

from makoto.schema import Finding
from makoto.lexicons import _ANSI_SGR_RX, _TEETH_FRAME_RX
from makoto.lib.io import iter_tool_events
from makoto.stopchecks._types import StopCheck

# gate.named_test — a NAMED-test pass-claim contradicted by that test's recorded FAILURE.
#
# The gate.green_claim DELTA. green_claim fires on a WHOLE-SUITE claim ("tests pass", "the suite is
# green") and DELIBERATELY firewalls to a universal subject — a named or subset claim fails open. This
# gate covers exactly that orthogonal slice: a claim that a SPECIFIC NAMED test passes ("`test_foo`
# passes", "test_bar is green"). A named test is coreference-PINNED, so the contradiction is precise:
#
#     a named-test pass-claim   ✗   a recorded FAILURE of THAT SAME named test, UNRESOLVED.
#
# Distinct from green_claim on every axis: SUBJECT is an exact test_\w+ id (not a universal suite
# head); the PIN is exact-name coreference (test_foo != test_foobar); the EVIDENCE is a per-test
# FAILED line for THAT name (not is_failing_testrun's run-level >=1-failed); DISCHARGE is a later
# recorded PASS of THAT SAME test (per-test, not "the most recent run is green").
#
# WHERE (stateless, over ctx.history): the per-name verdict is read from the recorded test-runner
# outputs in the faithful events history (full tool_response, ANSI-stripped). A FAILED record sets
# verdict[T]=FAIL; a later PASSED record discharges it to PASS; the claim fires iff a claimed name's
# CURRENT verdict is FAIL. FP-safety is the design (three corpus-measured guards): a pass predicate
# baked into the identifier or expectation-framed does not bind (#2); the named test framed as the
# EXCLUDED item of an enumerated count is out of scope (#3); a FAILED produced by mutation/teeth
# testing is not a material failure (#1).


# ---- lexicon (gate-specific, local — like stopcheck_fabricated_action) -----------------------

# A bare pytest-style test identifier. Exact token; coreference is by exact string equality.
_TESTNAME_RX = re.compile(r"\btest_[A-Za-z0-9_]+")
# A success predicate that can bind to a named-test subject in PROSE (the claim side).
_PASS_PRED_RX = re.compile(r"\b(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?)\b", re.IGNORECASE)
# Negation / forward-framing in the immediate claim clause -> not an assertion of present success.
_NEG_RX = re.compile(r"\b(?:not|never|no|fail(?:s|ed|ing)?|don['’]?t|doesn['’]?t|"
                     r"didn['’]?t|isn['’]?t|won['’]?t|can['’]?t)\b", re.IGNORECASE)
_FORWARD_RX = re.compile(r"\b(?:will|going\s+to|gonna|once|after|when|next|should|need(?:s)?\s+to|"
                         r"to\s+make|let['’]?s|I['’]?ll|expect(?:s|ed|ing)?)\b", re.IGNORECASE)
_SENT_SPLIT_RX = re.compile(r"(?<=[.!?])\s|\n")

# Recorded per-test FAILED / PASSED markers (the evidence side). Case-SENSITIVE runner tokens so
# prose like "failed to connect" never matches. Both orderings (verdict leads / trails the id).
_REC_FAIL_LEAD_RX = re.compile(r"^(?:FAILED|ERROR)\s+\S*?::(?P<name>test_[A-Za-z0-9_]+)", re.MULTILINE)
_REC_FAIL_TRAIL_RX = re.compile(r"::(?P<name>test_[A-Za-z0-9_]+)\b[^\n]*?\b(?:FAILED|ERROR)\b", re.MULTILINE)
_REC_PASS_LEAD_RX = re.compile(r"^(?:PASSED)\s+\S*?::(?P<name>test_[A-Za-z0-9_]+)", re.MULTILINE)
_REC_PASS_TRAIL_RX = re.compile(r"::(?P<name>test_[A-Za-z0-9_]+)\b[^\n]*?\b(?:PASSED)\b", re.MULTILINE)

# (#1) DELIBERATELY-INDUCED failure framing (a FAILED produced by mutation/teeth testing is not a
# material failure): _TEETH_FRAME_RX LIFTED to lexicons (consolidation T2.2, byte-identical) —
# second consumer is gate.stale_pass's claim teeth-window.

# (#3) An ENUMERATED suite count ("478/479 tests pass"): when the named test is introduced as the
# EXCLUDED item of such a count, "pass" binds to the count, not the name (green_claim's count rule).
_ENUM_COUNT_RX = re.compile(
    r"\b\d+\s*/\s*\d+\b|\b\d+\s+(?:tests?\s+)?(?:pass(?:ed|es|ing)?|green)\b", re.IGNORECASE)
_EXCLUDE_RX = re.compile(
    r"\b(?:flak(?:e|es|y|iness)|except|exclud\w*|excluding|known|pre-?existing|"
    r"skip\w*|ignor\w*|aside\s+from|other\s+than|unrelated|pollut\w*|leftover)\b", re.IGNORECASE)


def _external_pass_predicate(window: str) -> bool:
    """(#2) True iff a CLEAN pass predicate binds the name: one OUTSIDE every test_\\w+ identifier
    span AND not itself negated or forward/expectation-framed in its neighbourhood. In
    `test_main_is_green_on_real` the 'green' is part of the identifier; in '(expecting green-at-HEAD)
    is wrong' the external 'green' is an EXPECTATION — neither is a present-tense pass claim."""
    name_spans = [(m.start(), m.end()) for m in _TESTNAME_RX.finditer(window)]
    for pm in _PASS_PRED_RX.finditer(window):
        if any(s <= pm.start() and pm.end() <= e for s, e in name_spans):
            continue
        nb = window[max(0, pm.start() - 45):pm.end() + 25]
        if _NEG_RX.search(nb) or _FORWARD_RX.search(nb):
            continue
        return True
    return False


def claimed_passing_names(text: str) -> set:
    """The EXACT test names `text` asserts are PRESENTLY passing. A name qualifies iff it co-occurs
    with a CLEAN external pass predicate in its clause, not negated, not forward-framed, and not the
    excluded item of an enumerated count. A whole-suite claim (no test_\\w+ subject) yields nothing —
    that is green_claim's, deliberately out of scope here."""
    if not text:
        return set()
    out = set()
    for sent in _SENT_SPLIT_RX.split(text):
        if not _PASS_PRED_RX.search(sent):
            continue
        for nm in _TESTNAME_RX.finditer(sent):
            name = nm.group(0)
            a = nm.start()
            pre = sent[max(0, a - 80):a]
            clause = re.split(r"[,;:—]", pre)[-1]
            post = sent[nm.end():nm.end() + 40]
            if _NEG_RX.search(clause + " " + post):
                continue
            if _FORWARD_RX.search(clause):
                continue
            if _ENUM_COUNT_RX.search(sent) and _EXCLUDE_RX.search(sent[:a]):
                continue
            window = sent[max(0, a - 80):nm.end() + 60]
            if _external_pass_predicate(window):
                out.add(name)
    return out


def recorded_failed_names(text: str) -> set:
    """Exact test names recorded as FAILED/ERROR in a tool output (both verdict orderings)."""
    if not text:
        return set()
    return ({m.group("name") for m in _REC_FAIL_LEAD_RX.finditer(text)}
            | {m.group("name") for m in _REC_FAIL_TRAIL_RX.finditer(text)})


def recorded_passed_names(text: str) -> set:
    """Exact test names recorded as PASSED (the discharge evidence; both verdict orderings)."""
    if not text:
        return set()
    return ({m.group("name") for m in _REC_PASS_LEAD_RX.finditer(text)}
            | {m.group("name") for m in _REC_PASS_TRAIL_RX.finditer(text)})


def current_named_verdicts(history) -> dict:
    """{test_name: 'FAIL'|'PASS'} from the recorded test-runner outputs in `history`, in order.
    Last verdict wins (a fix-and-rerun-green discharges an earlier red; a re-fail re-opens). ANSI is
    stripped first (vitest/jest colorize verdict lines). A FAILED inside mutation/teeth framing (#1)
    is not recorded as a material failure."""
    verdict = {}
    for _tool, _cmd, resp in iter_tool_events(history):
        if not resp:
            continue
        resp = _ANSI_SGR_RX.sub("", resp)
        for nm in recorded_passed_names(resp):
            verdict[nm] = "PASS"
        if _TEETH_FRAME_RX.search(resp):
            continue                                  # deliberately-induced failure -> not material
        for nm in recorded_failed_names(resp):
            verdict[nm] = "FAIL"
    return verdict


def named_test_gate(text, *, history=()) -> Optional[Finding]:
    """Fire iff the assistant claims a SPECIFIC NAMED test passes while that exact test's CURRENT
    recorded verdict is FAILED (not discharged by a later recorded PASS of that same name). Silent on
    a whole-suite claim (green_claim's), a different test, a discharged test, or a claim with no
    recorded run of that name."""
    names = claimed_passing_names(text)
    if not names:
        return None
    verdict = current_named_verdicts(history)
    failing = sorted(nm for nm in names if verdict.get(nm) == "FAIL")
    if not failing:
        return None
    nm = failing[0]
    return Finding(
        pattern_id="gate.named_test",
        file="tests",
        line=0,
        level="error",
        message=(f"Claim states {nm} passes, but the most recent recorded run of that exact test "
                 f"shows it FAILED — re-run {nm} to green and cite it, or retract the claim."),
        retry_hint=f"Re-run {nm} and cite the green result, or narrow/retract the claim.",
    )


GATE = StopCheck(
    id="gate.named_test",
    fn=named_test_gate,
    run=lambda c: named_test_gate(c.text, history=c.history),
)
