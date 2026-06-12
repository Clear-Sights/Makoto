from __future__ import annotations
import re
from typing import Optional

from makoto.schema import Finding
from makoto.lib.claims import _code_spans
from makoto.stopchecks._common import turn_tool_calls
from makoto.stopchecks._types import StopCheck

# gate.fabricated_action — the assistant claims a completed TOOL action ("I ran `X`", "I executed
# scripts/deploy.sh") in a turn where it made NO tool calls at all. FP-safety is the whole design:
# a CLOSED tool-verb lexicon (reasoning verbs verified/checked/confirmed EXCLUDED — cognitive, not tool,
# claims), a DISTINCTIVE object (backticked command / path / URL — bare words like "tests" rejected),
# negation/future/quoted guards, and discharge on ANY tool activity this turn (turn_tool_calls > 0).
# The discharge is presence-of-work, NOT command-text matching: a real action is narrated in cleaned-up
# backticks (rel paths, simplified regex) and "invisible" tools (Workflow/Agent/Task) leave no Bash
# command — but every tool call DOES emit a PreToolUse event, so presence is the faithful, paraphrase-
# proof signal. Whether the spend was proportionate is a TEMPERANCE question, not this verity gate.

# closed lexicon of TOOL-shaped past-tense actions (NOT reasoning verbs)
_ACTION_VERB = r"(?:ran|executed|installed|fetched|cloned|pulled|pushed|deployed|launched)"
_ACTION_RX = re.compile(rf"\bI\s+{_ACTION_VERB}\s+(?P<obj>`[^`]+`|\S+)", re.I)
_NEG = re.compile(r"\b(?:not|never|without)\b|n't", re.I)
_FUTURE = re.compile(r"\b(?:will|going to|plan to|about to|let me)\b|i'?ll", re.I)


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
        obj = m.group("obj")
        if not _distinctive(obj):
            continue
        return obj.strip("`'\".,;:)(")
    return None


def fabricated_action_gate(text, *, history=()) -> Optional[Finding]:
    """Fire iff the assistant claims a completed tool action with a distinctive object
    (`_action_signal`) in a turn where it made ZERO tool calls (`turn_tool_calls(history) == 0`).
    Discharge: ANY tool activity this turn -> silent (real work backs the claim). Presence-of-work,
    not command-text matching: a real action is narrated in cleaned-up backticks and invisible tools
    (Workflow/Agent/Task) carry no Bash command, but every tool call emits a PreToolUse event — so
    presence is paraphrase-proof and invisible-tool-proof. Silent on no-claim or any tool work."""
    obj = _action_signal(text)
    if obj is None:
        return None
    if turn_tool_calls(history) > 0:
        return None                                   # real tool work this turn -> claim is backed
    return Finding(
        pattern_id="gate.fabricated_action", file="", line=0, level="error",
        message=(f"Claim states a completed tool action ('{obj}'), but this turn made no tool calls "
                 f"at all — actually run it (any tool counts) and cite the result, or remove the claim."),
        retry_hint="Actually run the command/tool, or drop the claim that you did it.")


GATE = StopCheck(
    id="gate.fabricated_action",
    fn=fabricated_action_gate,
    run=lambda c: fabricated_action_gate(c.text, history=c.history),
)
