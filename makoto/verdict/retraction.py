"""Surfaced-retraction detection + the reconcile decision (spec §4 retraction — L2).

A commitment is VALIDLY retracted only when the assistant EXPLICITLY drops it with a
subject-bound reason: reconcile's closed parameter set (R = a recorded result that
subject-binds the location, U = a real user contract change), or an explicit reason-bound
descope surfaced in prose (surfaced_retraction_locations). A commitment that merely VANISHES
with no surfaced reason is a HIDDEN retraction (detect_hidden_retraction) — exactly what the
advance gate must still catch, never silently honor. Firewall: NORMALIZED-EQUALITY membership
only (retracting cache.py never clears auth.py); fail-safe to the empty set on any internal
error (never mass-clear, never crash the hook). Stdlib only; no LLM, no HTTP.

Spec: docs/archive/specs/2026-05-31-makoto-bidirectional-falsifiability-design.md §4 (retraction).
"""
from __future__ import annotations
import re

from makoto.checks import detect_locations, normalize_path, subject_binds
from makoto.core.lexicons import (
    _NEG_FRAME_RX, _FENCE_SPAN_RX,
    _RETRACT_VERB_RX, _RETRACT_NEGPROMISE_RX, _RETRACT_POST_RX, _RETRACT_REASON_RX,
    _RETRACT_CLAUSE_BREAK_RX, _WRONG_SUBJECT_RX, _ACCIDENTAL_RX, _RETRACT_KEPT_RX,
    _RETRACT_ADVERSATIVE_RX,
)


def reconcile(commitment, *, reason_result_at=None, recorded=None,
              user_claims=False, contract_changed=False) -> str:
    """Decide whether an open commitment is VALIDLY retracted. Returns 'cleared'|'blocked'.

    Closed set of valid parameters:
      R = a recorded result whose key SUBJECT-BINDS (normalized equality) to the
          commitment location — proof the commitment is moot/impossible at its subject.
      U = the user changed the live contract section (a genuine supersession).
    Anything else stays blocked: an unbound reason (e.g. an empty fakeexcuse.txt that
    does not equal the commitment location), a forged user-claim with no contract
    change, or no verification at all. Hidden/unbound/unverified retractions never clear.
    """
    loc = commitment["location"]
    if reason_result_at is not None and recorded is not None:
        if subject_binds(loc, reason_result_at) and reason_result_at in recorded:
            return "cleared"                          # R: bound result proves it moot
        return "blocked"                              # unbound reason (the fakeexcuse firewall)
    if user_claims:
        return "cleared" if contract_changed else "blocked"   # U: only a real contract change
    return "blocked"


def detect_hidden_retraction(*, dropped: bool, reason) -> bool:
    """A commitment that VANISHES (dropped) with no surfaced reason is a HIDDEN
    retraction -> flag. A commitment still carried forward (not dropped) is not."""
    return bool(dropped) and not reason


# --- Surfaced retraction detection (the reconcile/retraction wiring) -----------------------
# Retraction vocab (_RETRACT_VERB_RX, _RETRACT_NEGPROMISE_RX, _RETRACT_POST_RX,
# _RETRACT_REASON_RX, _RETRACT_CLAUSE_BREAK_RX, _WRONG_SUBJECT_RX, _ACCIDENTAL_RX,
# _RETRACT_KEPT_RX, _RETRACT_ADVERSATIVE_RX) relocated to lexicons.py (L0) in Task 7.
# StopCheck functions and algorithm comments remain here.


def _fenced_spans(text: str):
    """Character ranges inside ``` code fences (quoted output, not the AI's own speech). Consumes the
    L0 single-source lexicons._FENCE_SPAN_RX (dedup U2) — the fence regex is defined in one place;
    substrate.claims._code_spans consumes the same object."""
    return [(m.start(), m.end()) for m in _FENCE_SPAN_RX.finditer(text)]


def _retract_interrogative_or_conditional(pre: str, after: str) -> bool:
    """A question ("Should I skip X?") or a conditional ("if tests fail we drop X") is not an
    actual retraction decision."""
    clause = pre.rsplit(".", 1)[-1]
    if re.search(r"\b(if|unless|when|whether|assuming|in case)\b", clause, re.I):
        return True
    if re.match(r"^\s*(?:should|shall|can|could|may|would|do|does|did)\s+(?:i|we)\b",
                clause.strip(), re.I):
        return True
    return "?" in after[:30]


def _retract_recommitted(text: str, loc: str, path_end: int) -> bool:
    """True if the SAME path is re-promised or produced AFTER its retraction (net still live):
    "going to skip X but I will add it", "un-dropping X — re-adding it now"."""
    tail = text[path_end:path_end + 180]
    base = re.escape(loc.rsplit("/", 1)[-1])
    return re.search(
        r"\b(?:re-?add\w*|add\w*|will add|keep\w*|ship\w*|implement\w*|creat\w*|"
        r"writ\w*|wrote|build\w*|built|includ\w*|restor\w*|put(?:ting)? (?:it )?back|"
        r"un-?drop\w*)\b[^.]{0,40}(?:" + base + r"|\bit\b)", tail, re.I) is not None


def surfaced_retraction_locations(text: str) -> set:
    """Return the set of normalized paths the assistant EXPLICITLY and REASON-BOUND retracts.

    Fail-safe: ANY internal error -> empty set (never mass-clear, never crash the hook)."""
    try:
        return _surfaced_retraction_locations(text or "")
    except Exception:
        return set()


def _surfaced_retraction_locations(text: str) -> set:
    if not text:
        return set()
    out = set()
    fenced = _fenced_spans(text)
    for loc, a, b in detect_locations(text):
        if any(s <= a < e for s, e in fenced):
            continue                                  # inside a code fence -> quoted output
        before = text[max(0, a - 80):a]
        after = text[b:b + 60]
        sentence = text[max(0, a - 120): b + 80]
        if _RETRACT_KEPT_RX.match(after):
            continue                                  # "X is still needed" -> explicitly KEPT
        has_reason = _RETRACT_REASON_RX.search(sentence) is not None
        bound = False
        # (1) an active retraction verb governing the path, same clause, before it, with reason
        for vm in _RETRACT_VERB_RX.finditer(before):
            between = before[vm.end():]
            if _RETRACT_CLAUSE_BREAK_RX.search(between) or _RETRACT_ADVERSATIVE_RX.search(between):
                continue                              # different clause / contrasted-away path
            pre = before[:vm.start()]
            if _NEG_FRAME_RX.search(pre[-40:]):
                continue                              # "not/never/n't ... skip" -> KEPT
            if _WRONG_SUBJECT_RX.search(pre[-25:]):
                continue                              # "you/they/the linter ... skip" -> not AI
            if _ACCIDENTAL_RX.search(pre[-40:]):
                continue                              # accidental loss, not a deliberate descope
            if _retract_interrogative_or_conditional(pre, after):
                continue
            if not has_reason:
                continue                              # bare drop, no reason -> HIDDEN, don't clear
            bound = True
            break
        # (1b) a negated production frame ("do not add X", "won't implement X") + reason
        if not bound and has_reason:
            for nm in _RETRACT_NEGPROMISE_RX.finditer(before):
                between = before[nm.end():]
                if _RETRACT_CLAUSE_BREAK_RX.search(between) or _RETRACT_ADVERSATIVE_RX.search(between):
                    continue
                pre = before[:nm.start()]
                if _WRONG_SUBJECT_RX.search(pre[-25:]):
                    continue                          # "you won't add X" -> not the AI's drop
                if _retract_interrogative_or_conditional(pre, after):
                    continue
                bound = True
                break
        # (2) a post-positive predicate after the path ("X is out of scope", "X can wait")
        if not bound:
            pm = _RETRACT_POST_RX.match(after) or _RETRACT_POST_RX.match(after.lstrip())
            if pm and not _NEG_FRAME_RX.search(after[:pm.end()]) and "?" not in after[:40]:
                bound = True
        if not bound:
            continue
        if _retract_recommitted(text, loc, b):
            continue                                  # re-promised/produced after -> still live
        out.add(normalize_path(loc))
    return out
