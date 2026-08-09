from __future__ import annotations
import re
from typing import Optional

from makoto.core.schema import Finding
from makoto.substrate.claims import _code_spans
import makoto.substrate.claim_graph as _claim_graph

# gate.fabricated_action — a concrete completed tool-action claim is certified only by a distinct,
# settled PostToolUse deed whose canonical command/executable target is identical. Read activity,
# a different command, and unsettled PreToolUse intent remain NOT-EVALUABLE and therefore block.
# The claim-side precision firewall remains closed: tool verbs only, distinctive object required,
# and negated/future/quoted/prior-turn frames excluded.

# closed lexicon of TOOL-shaped past-tense actions (NOT reasoning verbs)
_ACTION_VERB = r"(?:ran|executed|installed|fetched|cloned|pulled|pushed|deployed|launched)"
_ACTION_RX = re.compile(rf"\bI\s+{_ACTION_VERB}\s+(?P<obj>`[^`]+`|\S+)", re.I)
_NEG = re.compile(r"\b(?:not|never|without)\b|n't", re.I)
_FUTURE = re.compile(r"\b(?:will|going to|plan to|about to|let me)\b|i'?ll", re.I)
# PRIOR-TURN frame: the claim is a truthful RECAP of work done in an earlier turn/session, not an
# assertion that the action happened in the current turn. This frame stays scoped to the claim's
# own clause and fails open for explicit recaps.
_PRIOR_TURN = re.compile(
    r"\b(?:earlier|previously|already|before|last\s+turn|previous\s+turn|prior\s+turn|"
    r"this\s+session|in\s+the\s+last\s+turn|in\s+the\s+previous\s+turn|a\s+moment\s+ago)\b", re.I)


def _distinctive(obj: str) -> bool:
    """An object FP-safe enough to gate on: a backticked command, a path, or a URL. A bare prose
    word ('tests', 'X') is too FP-prone, so it is rejected (the agent must name a concrete target)."""
    if obj.startswith("`"):
        return True
    o = obj.strip("`'\".,;:)(")
    return bool("/" in o or o.endswith(".py") or o.startswith("http") or re.search(r"\.\w{2,4}$", o))


def _action_signal(text: str):
    """Return the claimed action object iff `text` asserts a completed tool action with a distinctive
    object; else None. Past-tense + first-person; negation/future/quoted excluded."""
    if not text:
        return None
    spans = _code_spans(text)
    for m in _ACTION_RX.finditer(text):
        if any(s <= m.start() < e for s, e in spans):
            continue                                  # the claim itself is quoted/fenced -> not own claim
        pre = text[max(0, m.start() - 24):m.start()]
        if _NEG.search(pre) or _FUTURE.search(pre):
            continue                                  # negated / future -> not a completed action
        # PRIOR-TURN recap: the claim is scoped to an earlier turn/session ("Earlier this session I
        # ran X", "I ran X previously"). Scan the claim's own sentence (the frame can lead or trail
        # the verb). The sentence is delimited cheaply on the surrounding terminators.
        s0 = max((text.rfind(p, 0, m.start()) for p in (". ", "! ", "? ", "\n")), default=-1) + 1
        e1 = min((p for p in (text.find(". ", m.end()), text.find("\n", m.end())) if p != -1),
                 default=len(text))
        if _PRIOR_TURN.search(text[s0:e1 + 1]):
            continue                                  # recap of an earlier turn -> not this-turn claim
        obj = m.group("obj")
        if not _distinctive(obj):
            continue
        return obj.strip("`'\".,;:)(")
    return None


def fabricated_action_gate(text, *, history=(), graph=None, claim_ids=()) -> Optional[Finding]:
    """Reject a concrete action claim without an exact settled-deed support path."""
    if graph is None:
        graph, claim_ids = _claim_graph.build_ephemeral_graph(text, history=history)
    claims = [
        graph.claims[claim_id] for claim_id in claim_ids
        if claim_id in graph.claims and graph.claims[claim_id].predicate.startswith("action.")
    ]
    if not claims:
        return None
    unsupported = next((
        claim for claim in claims
        if graph.adjudicate(claim.node_id).verdict is not _claim_graph.Verdict.CERTIFIED
    ), None)
    if unsupported is None:
        return None
    return Finding(
        pattern_id="gate.fabricated_action", file="", line=0, level="error",
        message=(f"Claim {unsupported.span_text!r} states a completed tool action, but no "
                 "settled deed with the "
                 "same canonical command/action target supports it — unrelated tool activity "
                 "cannot certify this claim."),
        retry_hint="Actually run the command/tool, or drop the claim that you did it.")


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.fabricated_action", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: fabricated_action_gate(
                   c.text, history=c.history, graph=c.claim_graph,
                   claim_ids=c.current_claim_ids))
