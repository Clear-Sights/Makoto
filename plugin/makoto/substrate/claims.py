"""L1 claim/admission primitives (split from predicates/helpers.py; renamed per §3c).

whole_suite_pass_claim gates a Stop payload's final message for a whole-suite green claim.
Imports L0 only.
"""
from __future__ import annotations
import re
from makoto.vocab import (
    _NEGATION_RX,
    _FENCE_SPAN_RX, _GREEN_CLAIM_RX, _SENTENCE_SPLIT_RX, _ADV_FORWARD_RX, _GREEN_UNIVERSAL_PREMOD,
)

# Compiled once at import, like every other pattern in this layer. `_INLINE_CODE_RX` is the
# inline-`backtick` half of _code_spans (the fenced half is the L0 single source).
_INLINE_CODE_RX = re.compile(r"`[^`\n]+`")
# The head's pre-modifier run: the CONTIGUOUS whitespace-separated word tokens immediately before
# the subject head, anchored at the head (\Z under endpos). Any non-word char — sentence
# punctuation, a colon, a checkbox bracket, a newline — terminates the run, so the walk-back
# respects exactly the clause/line boundaries the negation veto respects and a previous
# sentence's last word can never masquerade as the head's modifier.
_PREMOD_RUN_RX = re.compile(r"(?:\w+[ \t]+)+\Z")
# Right boundary for the success predicate — the same shape as vocab._DONE_TRAIL on the
# universal-done gate: the predicate must sit at a clause boundary (end of line/text, any
# punctuation, or a coordinating word), NOT flow into a content noun. 'the build passes
# ARGUMENTS to pytest' / 'the tests pass RATE' is the verb/noun used attributively, not a
# whole-suite green claim.
_PRED_TRAIL_RX = re.compile(
    r"(?=[^\S\n]*(?:$|\n|[^\w\s]|"
    r"(?:and|but|so|now|already|then|yet|finally|here|there|up|too|also|again)\b))",
    re.IGNORECASE)
# Post-match negation window terminator: the claim's own clause only.
_POST_CLAUSE_RX = re.compile(r"[,;.!?\n]|—|–")


# ---- whole-suite pass-claim signal (Theme A relocation, 2026-06-09) ----
# _code_spans relocated from stopchecks/_common.py in the same change: lib must not import
# stopchecks (layering), and the span primitive is pure text parsing — both stopcheck consumers
# (advance, green_claim) re-import it from here (L2 -> L1 down-edge, no shim).


def _code_spans(text: str):
    """Char ranges inside ``` fences OR inline `backticks` — a done-word there is QUOTED
    (code/output, e.g. the literal `done|complete|finished`), not the AI's own prose claim.
    The fenced half consumes the L0 single-source lexicons._FENCE_SPAN_RX (dedup U2).
    An UNTERMINATED trailing fence (a truncated final message) still opens a quoted span: from
    the dangling ``` to end-of-text everything is code/output, exactly the premise above —
    otherwise one missing closing fence exposes the whole quoted tail as prose."""
    spans = [m.span() for m in _FENCE_SPAN_RX.finditer(text)]
    dangling = text.find("```", spans[-1][1] if spans else 0)
    if dangling != -1:
        spans.append((dangling, len(text)))
    return spans + [m.span() for m in _INLINE_CODE_RX.finditer(text)]


def whole_suite_pass_claim(text: str):
    """The re.Match of a WHOLE-SUITE test-success claim in `text`, else None — a universal test
    subject (tests / the suite / CI / the build), not a subset, bound to a success predicate
    (pass / green), and not negated, forward-framed, or quoted from code/log output. Truthiness
    is EXACTLY the old stopcheck_green_claim._green_claim_signal bool (pure relocation, Theme A
    2026-06-09); the match POSITION additionally feeds stale_pass's teeth-framing window.

    The subset firewall is the head-vs-modifier split (the same shape as _advance_signal): the word
    immediately before the subject head must be a universal modifier (`the`/`all`/`every`/…) or
    absent. 'parser tests pass', 'these tests pass', 'the auth tests pass' all fail open — they
    assert a SLICE, not the whole suite, so an honest partial claim over a red full run never fires.
    The walk-back is CLAUSE-anchored (see _scoped_head), so a bare head after any prose still
    fires, and a partitive reached through function words ('some OF the tests pass') stays a
    subset. The predicate carries a right boundary (_PRED_TRAIL_RX), so an attributive or
    verb-complement use ('the build passes arguments to pytest') is not a green claim.

    named_test's named-subject machinery deliberately does NOT converge here: its negation/forward
    lexicons differ by measured design (_NEG_RX includes fail*, _FORWARD_RX includes expect*) —
    merging would change verdicts or hollow this helper into pure parameters."""
    if not text:
        return None
    spans = _code_spans(text)
    for m in _GREEN_CLAIM_RX.finditer(text):
        a = m.start()
        if any(s <= a < e for s, e in spans):
            continue                                   # quoted from code/log output, not a claim
        pre = text[max(0, a - 60):a]
        pre_clause = _SENTENCE_SPLIT_RX.split(pre)[-1]
        if _NEGATION_RX.search(pre_clause.rsplit(",", 1)[-1]):
            continue                                   # 'tests do not pass'
        # The FORWARD veto scans the whole preceding sentence, NOT just the last comma-clause: a
        # fronted conditional ('Once you rebase, all tests pass.') is punctuated with exactly the
        # comma the old rsplit truncated at, bypassing a firewall _ADV_FORWARD_RX names.
        if _ADV_FORWARD_RX.search(pre_clause):
            continue                                   # 'once tests pass', 'will pass'
        if not _PRED_TRAIL_RX.match(text, m.end()):
            continue                                   # 'the build passes ARGUMENTS to pytest'
        # Post-match negation, bounded to the claim's own clause ('the CI green ... never ...').
        if _NEGATION_RX.search(_POST_CLAUSE_RX.split(text[m.end():m.end() + 60])[0]):
            continue
        if _scoped_head(text, a, m.group("subj")):
            continue
        return m
    return None


def _scoped_head(text: str, a: int, subj: str) -> bool:
    """True iff the subject head at `a` is SCOPED to a subset — the scope firewall.

    Walks the head's contiguous pre-modifier run (clause/line-bounded by _PREMOD_RUN_RX, so a
    previous sentence never leaks in and a bare head after any prose still fires). A DIGIT
    ('244 tests passing', 'all 53 tests pass') is an ENUMERATED count — not a universal claim,
    and out of scope (matching a count to the run is the un-FP-safe quantity gate makoto already
    cut). A non-universal WORD touching the head ('parser tests', 'these tests') scopes a
    SUBSET. A PARTITIVE reached through universal tokens ('some/most/half/3 OF the tests')
    scopes a subset too — the 'of' hands scope to its left neighbour, which only 'all'/'every'
    keeps universal. All of those fail open; a word OUTSIDE the noun phrase after a universal
    quantifier ('...and ALL tests pass') just ends the walk, so only a bare or
    universally-quantified whole-suite head ('tests', 'all tests', 'the test suite') fires."""
    run = _PREMOD_RUN_RX.search(text, 0, a)
    tokens = run.group(0).split() if run else []
    tokens.reverse()                                   # nearest-to-head first
    seen_universal = False
    k = 0
    while k < len(tokens):
        t = tokens[k]
        tl = t.lower()
        if tl == "test":
            if k == 0 and subj.lower() == "suite":
                k += 1                                 # 'the test suite' connector -> keep walking
                continue
            return not seen_universal                  # 'test tests pass' -> subset
        if t.isdigit():
            return not seen_universal                  # enumerated count -> subset
        if tl in _GREEN_UNIVERSAL_PREMOD:
            seen_universal = True                      # universal quantifier -> keep walking
            k += 1
            continue
        if tl == "of" and seen_universal:              # partitive: scope is the word left of 'of'
            nxt = tokens[k + 1].lower() if k + 1 < len(tokens) else ""
            if nxt in ("all", "every"):
                seen_universal = True                  # 'all of the tests pass' stays universal
                k += 2
                continue
            return True                                # 'some/most/half/3 of the tests' -> subset
        return not seen_universal                      # restricting word touches the head -> subset
    return False
