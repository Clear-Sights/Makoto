from __future__ import annotations
from typing import Optional

from makoto.core.schema import Finding
from makoto.core.lexicons import _RUN_INTENT_CLAIM_RX, _RUN_INTENT_IDIOM_VETO_RX, _NEGATION_RX
from makoto.substrate.claims import _code_spans
from makoto.substrate.io import decode_history_row

# gate.run_promised -- the forward-looking sibling of gate.claimed_running: the immediately PRIOR
# turn's own message promised a first-person run-intent action ("I'll run the tests", "I'm going
# to restart the server", "let me deploy this") but this session's own recorded history shows NO
# Bash call at all in the turn that followed -- the word must match the world, checked one turn
# later.
#
# GRACE PERIOD BY CONSTRUCTION: this gate never reads the CURRENT Stop's own last_assistant_message
# -- only `history` is consulted, and `history` never contains the row for the Stop currently being
# evaluated (`_dispatch.py::_select_recent`'s `id < event_id`). A promise made THIS turn is
# therefore structurally exempt from blocking THIS Stop; it can only ever be checked starting at
# the NEXT Stop, once the intervening turn's tool calls are themselves in history. This is the
# literal, structural form of "discharged by the next message" -- not a timestamp or counter kept
# anywhere, just which rows have and haven't been ingested yet.
#
# STATELESS BY DESIGN: no new persistence. Every hook event this session fires -- Stop included,
# `last_assistant_message` and all -- is already durably logged by `_dispatch.py::_ingest_event`
# BEFORE any handler runs, so a prior turn's own claim is directly re-derivable from `ctx.history`
# at the next Stop. This deliberately does NOT extend `Plan`/`PlanNode` (SPEC-5, see
# `makoto/session/plan.py`): a Plan node's discharge evidence is a LOCATED file write
# (`contractOrder.py`'s `_event_location`/`Plan.resolve`, keyed by `where`), but a run-intent
# promise's only evidence is "a Bash call happened" -- there is no `where` to resolve against.
# Same enforcement SHAPE Plan/gate.contract_order established (declare a forward commitment ->
# must discharge -> Stop blocks if not), a structurally different mechanism because the discharge
# evidence itself is structurally different.
#
# CLOSED LEXICON (core/lexicons.py's `_RUN_INTENT_CLAIM_RX`): a first-person FORWARD auxiliary
# ("I'm going to" / "I'll" / "let me" / "I plan to") bound to a closed process-lifecycle verb set
# mirroring gate.claimed_running's own `_PROCESS_START_VERB_RX` vocabulary (run/launch/deploy/...),
# base/infinitive form. Closed subject AND closed verb by construction: "it's going to rain today"
# cannot match on either axis. Bare "start" is excluded from the shared verb set (too overloaded
# for beginning any activity, not specifically a process) unless paired with a closed process-
# object noun ("start the server"). Idiom vetoes on "run" specifically: "run X by Y" (approval-
# seeking), "run through X" (walkthrough), "run the/some numbers" (mental math) are none of them
# execution intent.
#
# DISCHARGE EVIDENCE: ANY Bash call in the turn following the promise, full stop -- not a match
# against the promised text's specific content. Reliably mapping "the tests" or "this" to a
# specific expected command is an open text-understanding problem outside this gate's scope (and a
# wrong guess there is itself a zero-FP violation risk); "did the assistant run ANYTHING at all
# after promising to run something" is the bound that stays provably safe.
#
# SCOPE (documented, not fixed here): only the immediately PRIOR turn's promise is ever checked --
# a promise from two-or-more turns back that was already checked (and silently passed, or whose
# checking Stop never fired for some other reason) is not re-litigated. Same 1-hour rolling window
# every history-based gate in this catalog already lives with (`_select_recent`).


def _run_intent_claim(text: str):
    """Return the re.Match of a first-person forward run-intent promise in `text`, else None.
    Mirrors claimedRunningAbsent._running_claim's shape: quoted/fenced spans excluded, a negated
    match voided, an idiom veto checked on the text immediately trailing the match, a question
    (the containing sentence ends '?') voided."""
    if not text:
        return None
    spans = _code_spans(text)
    for m in _RUN_INTENT_CLAIM_RX.finditer(text):
        a, b = m.start(), m.end()
        if any(s <= a < e for s, e in spans):
            continue                                  # quoted/fenced -> not the agent's own prose claim
        if _NEGATION_RX.search(m.group(0)):
            continue                                  # "I'll never run ..." -- filler swallowed 'never'
        if _RUN_INTENT_IDIOM_VETO_RX.search(text[b:b + 40]):
            continue                                  # "run it by you" / "run through" / "run the numbers"
        stop = len(text)
        for i in range(b, min(len(text), b + 200)):
            if text[i] in ".!?\n":
                stop = i
                break
        if text[stop:stop + 1] == "?":
            continue                                  # a question, not a declarative promise
        return m
    return None


def _last_stop_index(history) -> Optional[int]:
    """The index (in `history`, session order) of the most recent Stop/SubagentStop-event row, or
    None if neither appears anywhere in the window. `history` is already `ORDER BY ts`
    (_select_recent) -- treated as one equivalence class the same way `_dispatch.py` itself
    documents them ("Gates evaluate on Stop AND SubagentStop")."""
    idx = None
    for i, row in enumerate(history or ()):
        ev = decode_history_row(row)
        if isinstance(ev, dict) and ev.get("hook_event_name") in ("Stop", "SubagentStop"):
            idx = i
    return idx


def _bash_call_after(history, idx: int) -> bool:
    """True iff a PostToolUse Bash call appears anywhere after position `idx` in `history`."""
    for row in list(history or ())[idx + 1:]:
        ev = decode_history_row(row)
        if (isinstance(ev, dict) and ev.get("hook_event_name") == "PostToolUse"
                and ev.get("tool_name") == "Bash"):
            return True
    return False


def run_promised_gate(*, history=()) -> Optional[Finding]:
    """Fire iff the immediately PRIOR turn's own message made a run-intent promise
    (`_run_intent_claim`) and no Bash call appears anywhere in `history` since -- the one-turn
    grace period is structural (see module docstring), not computed here. Silent whenever no prior
    Stop/SubagentStop exists yet, the prior message made no such promise, or ANY Bash call
    discharged it."""
    history = list(history or ())
    idx = _last_stop_index(history)
    if idx is None:
        return None
    prior = decode_history_row(history[idx])
    prior_text = (prior or {}).get("last_assistant_message") or ""
    claim = _run_intent_claim(prior_text)
    if claim is None:
        return None
    if _bash_call_after(history, idx):
        return None
    return Finding(
        pattern_id="gate.run_promised", file="", line=0, level="error",
        message=(f"Last turn promised to run something (\"{claim.group(0).strip()}\") but no "
                  "Bash call appears anywhere in this session's recorded history since -- the "
                  "word must match the world."),
        retry_hint=("Actually run it with a real Bash call, or retract/rescope the promise "
                     "before ending the turn."))


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.run_promised", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: run_promised_gate(history=c.history))
