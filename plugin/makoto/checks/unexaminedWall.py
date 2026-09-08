"""gate.unexamined_wall -- the agent says a thing cannot be known, having done nothing to find out.

Register entry G5, WALL WITHOUT INVENTORY: "cannot" declared with the means already held; the
fix line is "list what you hold before saying no". The entry has existed with no runner, which
is entry B7 (a rule written and enforced nowhere) applied to G5. This is the runner.

WHAT IT IS NOT. It does not judge whether a refusal was correct, and it does not read the
operator's words. Its subject is the assistant's own statement held against the assistant's own
act stream, which is the ordinary Makoto bar.

THE COUNTABLE CORE, and why it is this and not something wider. "The means were held" is, in
general, a question about whether some act would have answered the claim -- a similarity
question, and similarity is judgement. There is one case where it is countable instead: an
EPISTEMIC cannot -- a claim that something cannot be determined, told, checked or known --
issued when the agent has taken NO act at all since the operator last spoke. Absence of the
whole channel is countable in a way that "insufficient acts" never is, which is the same
0-FP construction `claimedConsentAbsent` rests on. A claim about what is knowable, made
without a single act in the window, is a wall with the inventory unopened by construction.

Two claim shapes are deliberately EXCLUDED because they are not epistemic and not falsifiable
by acting: a refusal of a request ("I won't", "I can't help with"), and a statement of absent
capability in the abstract ("models cannot browse"). Neither asserts that a fact about THIS
work is unknowable, so neither is G5.

THE WINDOW is the calls since the operator's last genuine turn (`last_operator_turn_ts` +
`calls_since`), not the whole session, and the direction matters: over a whole session the
"has acted" predicate is monotone, so one early call would silence the gate forever. Windowing
asks the question G5 actually asks -- did you look BEFORE saying no, this time.

STATED LIMITS, on the record rather than discovered later:

  1. An agent that makes one unrelated call and then declares a wall is NOT caught. Relating
     the call to the claim is the similarity question refused above.
  2. G1 (goal substitution), G2 (determined asked as open) and G3 (scope below the answer) get
     no runner here and none elsewhere. Each needs a comparison of the request against the
     result, or of a question against what was derivable -- both similarity. They are named
     here so their absence is a choice on the record. Measured against two real G2 incidents,
     a zero-acts test catches neither, because in both the agent had acted extensively and
     asked anyway; any honest G2 runner must compare the question to the read set, not count
     acts.
"""
from __future__ import annotations
import re

from makoto.state.ledger import last_operator_turn_ts
from makoto.substrate._canonAtoms import calls_since
from makoto.vocab import Finding

# An EPISTEMIC cannot: the claim is that a fact cannot be established. Not a refusal, not a
# statement about capabilities in general -- those are excluded by design, see the docstring.
_WALL_RX = re.compile(
    r"\b(?:"
    r"(?:there\s+is|there's)\s+no\s+way\s+to\s+(?:tell|know|check|determine|verify|find\s+out)"
    r"|(?:i|we)\s+(?:can(?:no|')t|cannot|am\s+unable\s+to|are\s+unable\s+to)\s+"
    r"(?:tell|know|check|determine|verify|find\s+out|establish)"
    r"|(?:it|this|that)\s+(?:is|'s)\s+(?:impossible|not\s+possible)\s+to\s+"
    r"(?:tell|know|check|determine|verify)"
    r"|no\s+way\s+of\s+(?:knowing|telling|checking|determining)"
    r"|(?:i|we)\s+have\s+no\s+way\s+to\s+(?:tell|know|check|determine|verify)"
    r")\b", re.IGNORECASE)

RETRY_HINT = ("You state that something cannot be determined, but you have taken no action since "
              "the operator last spoke. List what you hold and act on it first; if the claim "
              "survives the attempt, say what you tried and what it returned.")
DESCRIPTION = ("Blocks a claim that something cannot be determined when the agent has taken no "
               "action at all since the operator's last turn.")


def unexamined_wall_gate(text, *, history=None, transcript_path=None):
    """One BLOCKING Finding when an epistemic cannot is stated with an empty act window.

    Never raises. Every failure to establish the window reads as NO EVIDENCE and the check is
    silent, because the alternative -- blocking a turn on a decode failure -- is a gate resting
    on a false fact. Note the asymmetry that keeps that safe: `calls_since` widens the window
    when the boundary cannot be read, so an unreadable transcript yields MORE calls, never
    fewer, and this gate only fires on zero."""
    wall = _WALL_RX.search(text or "")
    if not wall:
        return None
    try:
        since = last_operator_turn_ts(transcript_path)
    except Exception:
        return None
    if since is None:
        # No operator turn to window against. The claim may still be a wall, but the question
        # this gate asks -- did you look before saying no, THIS time -- has no boundary, and a
        # window that cannot be established must never widen what is blocked.
        return None
    try:
        acts = calls_since(history, since)
    except Exception:
        return None
    if acts:
        return None
    return Finding(
        pattern_id="gate.unexamined_wall",
        file="", line=0, level="error",
        message=(f"Claim that a fact cannot be established ({wall.group(0)!r}), with no action "
                 f"taken since the operator last spoke — the inventory was never opened."),
        retry_hint=RETRY_HINT,
    )


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unexamined_wall", applies_at="Stop", posture="BLOCK",
               may_block=True, tests="CLAIM_VS_HISTORY",
               keywords=("no way to tell", "no way to know", "cannot determine",
                         "can't tell", "no way of knowing", "unable to verify"),
               retry_hint=RETRY_HINT, description=DESCRIPTION,
               eats=frozenset({"text", "history", "transcript_path"}),
               run=lambda c: unexamined_wall_gate(c.text, history=c.history,
                                                  transcript_path=c.transcript_path))
