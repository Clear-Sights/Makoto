from __future__ import annotations
import re
from typing import Optional

from makoto.vocab import Finding
from makoto.vocab import _ANSI_SGR_RX, _TEETH_FRAME_RX, _SENTENCE_SPLIT_RX
from makoto.kit import is_test_runner, iter_tool_events

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


# ---- lexicon (gate-specific, local — like gate.fabricated_action) -----------------------

# A bare pytest-style test identifier. Exact token; coreference is by exact string equality.
_TESTNAME_RX = re.compile(r"\btest_[A-Za-z0-9_]+")
# A success predicate that can bind to a named-test subject in PROSE (the claim side).
_PASS_PRED_RX = re.compile(r"\b(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?)\b", re.IGNORECASE)
# Negation / forward-framing in the immediate claim clause -> not an assertion of present success.
_NEG_RX = re.compile(r"\b(?:not|never|no|fail(?:s|ed|ing)?|don['’]?t|doesn['’]?t|"
                     r"didn['’]?t|isn['’]?t|won['’]?t|can['’]?t)\b", re.IGNORECASE)
_FORWARD_RX = re.compile(r"\b(?:will|going\s+to|gonna|once|after|when|next|should|need(?:s)?\s+to|"
                         r"to\s+make|let['’]?s|I['’]?ll|expect(?:s|ed|ing)?)\b", re.IGNORECASE)
# The clause boundary that isolates the text immediately governing the name.
_CLAUSE_SPLIT_RX = re.compile(r"[,;:—]")
# One actual quoted run (straight or curly), single-line: the (#4) exemption is span-membership.
_QUOTE_SPAN_RX = re.compile(r'"[^"\n]*"|“[^”\n]*”')
# Sentence split reuses vocab._SENTENCE_SPLIT_RX -- this file held the repo's last
# byte-identical private copy; every other consumer already imports the vocab object.

# Recorded per-test FAILED / PASSED markers (the evidence side). Case-SENSITIVE runner tokens so
# prose like "failed to connect" never matches. Both orderings (verdict leads / trails the id).
# The lead forms tolerate a line PREFIX before the verdict token (pytest-xdist emits
# "[gw0] [100%] PASSED tests/…::test_x"; the old ^-anchor recorded that runner's FAILED via the
# short-summary line but never its PASSED, so a real red became undischargeable). The id captures
# the MODULE PATH (the header's "exact test id" pin — a bare-name key let tests/a's failure deny a
# claim about tests/b's same-named green test) and any PARAMETRIZATION suffix (stripping it let a
# green test_charge[eur] discharge a red test_charge[usd]).
_TEST_ID = r"(?P<path>\S*?)::(?P<name>test_[A-Za-z0-9_]+(?:\[[^\]\n]*\])?)"
_REC_FAIL_LEAD_RX = re.compile(r"^[^\n]*?\b(?:FAILED|ERROR)\s+" + _TEST_ID, re.MULTILINE)
_REC_FAIL_TRAIL_RX = re.compile(_TEST_ID + r"[^\n]*?\b(?:FAILED|ERROR)\b", re.MULTILINE)
_REC_PASS_LEAD_RX = re.compile(r"^[^\n]*?\bPASSED\s+" + _TEST_ID, re.MULTILINE)
_REC_PASS_TRAIL_RX = re.compile(_TEST_ID + r"[^\n]*?\bPASSED\b", re.MULTILINE)
# (#1)/(#2) teeth-frame SCOPE: the frame voids only verdict records in its own vicinity (this
# many chars around the record), never the whole response — one incidental teeth word in a
# traceback must not discard every recorded failure in the run, and symmetrically a PASSED
# recorded inside deliberately-induced-failure framing is no material discharge either.
_TEETH_SCOPE_BEFORE = 200
_TEETH_SCOPE_AFTER = 120

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
    for sent in _SENTENCE_SPLIT_RX.split(text):
        if not _PASS_PRED_RX.search(sent):
            continue
        # (#4) QUOTED material: citing a phrase to examine, correct, or retract it — e.g. 'my
        # sentence ("...test_foo now pass") reads as a claim... retracting it' — is not itself a
        # fresh, present-tense assertion. The neg/forward checks below only see a small window
        # local to the name; a retraction two sentences later is invisible to them, so a quoted
        # span is excluded here regardless of what surrounds it. The exemption is a SPAN test
        # (the name must lie inside one actual quoted run), not a loose any-quote-before-and-
        # after test — 'the "smoke" tier: test_charge passes and the "core" tier too' quotes two
        # OTHER words, and its genuine claim over test_charge must still bind.
        quote_spans = [m.span() for m in _QUOTE_SPAN_RX.finditer(sent)]
        for nm in _TESTNAME_RX.finditer(sent):
            name = nm.group(0)
            a, b = nm.start(), nm.end()
            if any(s <= a and b <= e for s, e in quote_spans):
                continue
            # The CLAUSE containing the name bounds every binding decision — negation, forward
            # framing, and the pass predicate itself. A predicate in a DIFFERENT clause
            # ("test_charge is quarantined, everything else passes") governs different material
            # and must not bind to this name.
            cstart = 0
            for m in _CLAUSE_SPLIT_RX.finditer(sent, 0, a):
                cstart = m.end()
            cm = _CLAUSE_SPLIT_RX.search(sent, b)
            cend = cm.start() if cm else len(sent)
            pre = sent[max(cstart, a - 80):a]
            post = sent[b:min(cend, b + 40)]
            if _NEG_RX.search(pre + " " + post):
                continue
            if _FORWARD_RX.search(pre):
                continue
            if _ENUM_COUNT_RX.search(sent) and _EXCLUDE_RX.search(sent[:a]):
                continue
            window = sent[max(cstart, a - 80):min(cend, b + 60)]
            if _external_pass_predicate(window):
                out.add(name)
    return out


def _recorded_names(text: str, lead_rx, trail_rx) -> set:
    """Shared shape of recorded_failed_names/recorded_passed_names (found alpha-equivalent by AST
    canonicalization, 2026-07-09) -- same extraction, different verdict regex pair."""
    if not text:
        return set()
    return ({m.group("name") for m in lead_rx.finditer(text)}
            | {m.group("name") for m in trail_rx.finditer(text)})


def recorded_failed_names(text: str) -> set:
    """Exact test names recorded as FAILED/ERROR in a tool output (both verdict orderings)."""
    return _recorded_names(text, _REC_FAIL_LEAD_RX, _REC_FAIL_TRAIL_RX)


def recorded_passed_names(text: str) -> set:
    """Exact test names recorded as PASSED (the discharge evidence; both verdict orderings)."""
    return _recorded_names(text, _REC_PASS_LEAD_RX, _REC_PASS_TRAIL_RX)


def current_named_verdicts(history) -> dict:
    """{full_test_id: 'FAIL'|'PASS'} from the recorded TEST-RUNNER outputs in `history`, in
    order. The key is the exact recorded id — `path::name[param]` — matching the header's
    "exact test id" pin (a bare-name key let tests/a's failure shadow tests/b's same-named
    test, and let one parametrized case discharge another). Only responses of a recognized
    test-runner invocation are read (`kit.is_test_runner` on the recorded command): a FAILED
    line the agent merely DISPLAYED — `cat old.log` — is not a run and must never ground a
    DENY. Within one response, records apply in TEXTUAL ORDER and the last verdict wins (a
    run-fix-rerun sequence captured in one Bash call ends on its true final verdict), exactly
    as the last verdict wins across responses (a fix-and-rerun-green discharges an earlier
    red; a re-fail re-opens). ANSI is stripped first (vitest/jest colorize verdict lines). A
    verdict recorded inside mutation/teeth framing (#1) is not material — scoped to the
    record's own vicinity (`_TEETH_SCOPE_*`), never the whole response, and applied
    SYMMETRICALLY: a framed FAILED is no material failure, and a framed PASSED (a pass under
    deliberately-induced-failure framing is evidence the test cannot fail) is no material
    discharge either."""
    verdict = {}
    for _tool, cmd, resp in iter_tool_events(history):
        if not resp or not is_test_runner(cmd or ""):
            continue
        resp = _ANSI_SGR_RX.sub("", resp)
        # Short-circuit through the shared per-name parsers (the same evidence primitives
        # kit.compute_delta reuses) before the positioned scan below: most runner responses
        # carry no per-test verdict lines at all.
        if not (recorded_failed_names(resp) or recorded_passed_names(resp)):
            continue
        records = []
        for rx, v in ((_REC_FAIL_LEAD_RX, "FAIL"), (_REC_FAIL_TRAIL_RX, "FAIL"),
                      (_REC_PASS_LEAD_RX, "PASS"), (_REC_PASS_TRAIL_RX, "PASS")):
            for m in rx.finditer(resp):
                records.append(
                    (m.start(), m.end(), f'{m.group("path")}::{m.group("name")}', v))
        for start, end, tid, v in sorted(records):
            window = resp[max(0, start - _TEETH_SCOPE_BEFORE):end + _TEETH_SCOPE_AFTER]
            if _TEETH_FRAME_RX.search(window):
                continue                              # deliberately-induced -> not material
            verdict[tid] = v
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
    # A prose claim names a BARE test function; the recorded verdicts carry exact ids
    # (path::name[param]). Group the recorded ids by module path: parametrized cases of one
    # function are ONE family (a green test_charge[eur] never discharges a red
    # test_charge[usd]), while same-named functions in DIFFERENT modules are DISTINCT candidate
    # referents of the bare name — DENY only when EVERY candidate family holds a red, because a
    # DENY over an ambiguous name that might refer to a green test rests on a false fact.
    failing = []
    for nm in sorted(names):
        families = {}
        for tid, v in verdict.items():
            path, _, ident = tid.rpartition("::")
            if ident.split("[", 1)[0] == nm:
                families.setdefault(path, []).append((tid, v))
        if not families:
            continue
        red_ids = []
        every_family_red = True
        for members in families.values():
            fam_red = sorted(tid for tid, v in members if v == "FAIL")
            if fam_red:
                red_ids.extend(fam_red)
            else:
                every_family_red = False
        if every_family_red and red_ids:
            failing.append((nm, sorted(red_ids)[0]))
    if not failing:
        return None
    nm, red_id = failing[0]
    return Finding(
        pattern_id="gate.named_test",
        file="tests",
        line=0,
        level="error",
        message=(f"Claim states {nm} passes, but the most recent recorded run of that exact test "
                 f"({red_id}) shows it FAILED — re-run {nm} to green and cite it, or retract "
                 f"the claim."),
        retry_hint=f"Re-run {nm} and cite the green result, or narrow/retract the claim.",
    )


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.named_test", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="TESTRUN_DELTA",
               eats=frozenset({"text", "history"}),
               run=lambda c: named_test_gate(c.text, history=c.history))
