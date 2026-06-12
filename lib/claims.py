"""L1 claim/admission primitives (split from predicates/helpers.py; renamed per §3c).

claims_done / claims_success gate a Stop payload's final message. Imports L0 only.
"""
from __future__ import annotations
import re
from makoto.lexicons import (
    _DONE_WORDS_RX, _NEGATION_RX, _SUCCESS_WORDS_RX,
    _FENCE_SPAN_RX, _GREEN_CLAIM_RX, _SENTENCE_SPLIT_RX, _ADV_FORWARD_RX, _GREEN_UNIVERSAL_PREMOD,
)


def claims_done(payload: dict) -> bool:
    """True iff the Stop payload represents a real 'done' claim worth gating on.

    PRODUCTION-PAYLOAD FIX (2026-05-29, verified vs 1759 real captured Stop events):
    Claude Code's real Stop hook payload exposes the assistant's final message as
    ``last_assistant_message`` and carries NO ``stop_reason`` key. The original spec
    (mirroring install-helpers/predicates.sh) read ``response`` and required
    ``stop_reason == 'end_turn'`` — both ABSENT in production, so this helper always
    returned False and patterns 2.1/2.2/2.5 were DEAD in production while their unit
    tests passed on manufactured payloads. See docs/ADVERSARY-FINDINGS.md.

    Gating contract (corrected):
      1. stop_reason, IF PRESENT, must be 'end_turn' (skips tool_use / max_tokens
         stops in payloads that carry the field). A Stop event with no stop_reason is
         end-of-turn by definition, so its absence is NOT a rejection.
      2. The assistant text (``last_assistant_message`` in prod; ``response`` retained
         for the bash-port / synthetic-test payload shape) MUST be non-empty.
      3. The text MUST contain a done-word (done|complete|completed|finished, case-insensitive).
      4. The 50-char window BEFORE the first done-word MUST NOT contain a negation
         token (not|never|no|n’t|n’’t) — captures ‘I am not done’, ‘haven’t finished’, etc.
    """
    stop_reason = payload.get("stop_reason")
    if stop_reason is not None and stop_reason != "end_turn":
        return False
    response = payload.get("last_assistant_message") or payload.get("response", "")
    if not response:
        return False
    m = _DONE_WORDS_RX.search(response)
    if m is None:
        return False
    # 50-char negation window before the first done-word.
    before = response[: m.start()]
    window = before[-50:] if len(before) > 50 else before
    if _NEGATION_RX.search(window):
        return False
    return True


def claims_success(payload: dict) -> Optional[re.Match]:
    """Like claims_done but with the WIDE lexicon. Returns the re.Match of the
    first success word (negation-window guarded), else None."""
    stop_reason = payload.get("stop_reason")
    if stop_reason is not None and stop_reason != "end_turn":
        return None
    response = payload.get("last_assistant_message") or payload.get("response", "")
    if not response:
        return None
    m = _SUCCESS_WORDS_RX.search(response)
    if m is None:
        return None
    before = response[: m.start()]
    window = before[-50:] if len(before) > 50 else before
    if _NEGATION_RX.search(window):
        return None
    return m


# ---- whole-suite pass-claim signal (Theme A relocation, 2026-06-09) ----
# _code_spans relocated from stopchecks/_common.py in the same change: lib must not import
# stopchecks (layering), and the span primitive is pure text parsing — both stopcheck consumers
# (advance, green_claim) re-import it from here (L2 -> L1 down-edge, no shim).


def _code_spans(text: str):
    """Char ranges inside ``` fences OR inline `backticks` — a done-word there is QUOTED
    (code/output, e.g. the literal `done|complete|finished`), not the AI's own prose claim.
    The fenced half consumes the L0 single-source lexicons._FENCE_SPAN_RX (dedup U2)."""
    spans = [(m.start(), m.end()) for m in _FENCE_SPAN_RX.finditer(text)]
    spans += [(m.start(), m.end()) for m in re.finditer(r"`[^`\n]+`", text)]
    return spans


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
        clause = _SENTENCE_SPLIT_RX.split(pre)[-1].rsplit(",", 1)[-1]
        if _NEGATION_RX.search(clause):
            continue                                   # 'tests do not pass'
        if _ADV_FORWARD_RX.search(clause):
            continue                                   # 'once tests pass', 'will pass'
        # scope firewall: walk back over the head's modifiers. A DIGIT ('244 tests passing', 'all
        # 53 tests pass') is an ENUMERATED count — not a universal claim, and out of scope (matching
        # a count to the run is the un-FP-safe quantity gate makoto already cut). A non-universal
        # WORD ('parser tests', 'these tests') scopes a SUBSET. Both fail open; only a bare or
        # universally-quantified whole-suite head ('tests', 'all tests', 'the test suite') fires.
        toks = re.findall(r"\w+", text[max(0, a - 40):a])
        scoped = False
        i = len(toks) - 1
        while i >= 0:
            t = toks[i]
            if t.isdigit():
                scoped = True                          # enumerated count -> out of scope
                break
            tl = t.lower()
            if tl in _GREEN_UNIVERSAL_PREMOD:
                if tl == "test":                       # 'test suite' connector -> keep walking back
                    i -= 1
                    continue
                break                                  # a universal quantifier -> whole-suite -> fire
            scoped = True                              # a restricting word -> subset
            break
        if scoped:
            continue
        return m
    return None


