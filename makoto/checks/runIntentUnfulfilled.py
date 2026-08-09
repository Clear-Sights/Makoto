from __future__ import annotations
from typing import Optional

from makoto.core.schema import Finding
from makoto.core.lexicons import _RUN_INTENT_CLAIM_RX, _RUN_INTENT_IDIOM_VETO_RX, _NEGATION_RX
from makoto.substrate.claims import _code_spans
from makoto.substrate.io import decode_history_row
import makoto.substrate.claim_graph as _claim_graph

# gate.run_promised -- the immediately prior Stop's first-person run promise is checked one turn
# later against the persisted graph. A deed discharges it only when it occurred after the promise
# and corefers with the promise's action class and canonical target. ``printf unrelated`` therefore
# cannot discharge a deploy release; a failed exact command still proves that it was attempted.
#
# GRACE PERIOD BY CONSTRUCTION: this gate never reads the CURRENT Stop's own last_assistant_message
# -- only `history` is consulted, and `history` never contains the row for the Stop currently being
# evaluated (`_dispatch.py::_select_recent`'s `id < event_id`). A promise made THIS turn is
# therefore structurally exempt from blocking THIS Stop; it can only ever be checked starting at
# the NEXT Stop, once the intervening turn's tool calls are themselves in history. This is the
# literal, structural form of "discharged by the next message" -- not a timestamp or counter kept
# anywhere, just which rows have and haven't been ingested yet.
#
# PERSISTENCE: the first Stop persists the promise claim before adjudication. Settled PostToolUse
# events persist deeds. The next Stop selects only the immediately prior promise for enforcement,
# while the receipt retains all claims and their verdicts.
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
# UNKNOWN TARGETS: pronouns or aliases that cannot be normalized without guessing stay visible as
# NOT-EVALUABLE. They never acquire a support edge from mere temporal proximity.
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
    None if neither appears anywhere in the window. `history` is already `ORDER BY id`
    (_select_recent) -- treated as one equivalence class the same way `_dispatch.py` itself
    documents them ("Gates evaluate on Stop AND SubagentStop")."""
    idx = None
    for i, row in enumerate(history or ()):
        ev = decode_history_row(row)
        if isinstance(ev, dict) and ev.get("hook_event_name") in ("Stop", "SubagentStop"):
            idx = i
    return idx


def _bash_call_after(history, idx: int) -> bool:
    """Legacy diagnostic: whether any PostToolUse Bash follows ``idx``.

    The blocking gate intentionally does not use this broad boolean; graph adjudication requires
    action-and-target coreference.
    """
    for row in list(history or ())[idx + 1:]:
        ev = decode_history_row(row)
        if (isinstance(ev, dict) and ev.get("hook_event_name") == "PostToolUse"
                and ev.get("tool_name") == "Bash"):
            return True
    return False


def run_promised_gate(*, history=(), graph=None, claim_ids=()) -> Optional[Finding]:
    """Reject the prior turn's promise unless a later target-coreferent deed supports it."""
    history = list(history or ())
    idx = _last_stop_index(history)
    if idx is None:
        return None
    if graph is None:
        graph = _claim_graph.ClaimGraph(session_id="ephemeral")
        _claim_graph.ingest_history(graph, history)
        _claim_graph.link_claims(graph, history=history)
        event_id = _claim_graph.history_event_id(history[idx], idx)
        claim_ids = [
            claim.node_id for claim in graph.claims.values()
            if str(claim.source_event_id) == str(event_id)
            and claim.predicate.startswith("promise.")
        ]
    claims = [
        graph.claims[claim_id] for claim_id in claim_ids
        if claim_id in graph.claims and graph.claims[claim_id].predicate.startswith("promise.")
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
        pattern_id="gate.run_promised", file="", line=0, level="error",
        message=(f"Last turn's claim {unsupported.span_text!r} promised "
                 f"{unsupported.predicate} on '{unsupported.target_value}', but no later "
                 "settled deed corefers with both "
                 "that action and target — unrelated Bash activity cannot discharge it."),
        retry_hint=("Actually run the promised target with a real tool call, or retract/rescope the promise "
                     "before ending the turn."))


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.run_promised", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: run_promised_gate(
                   history=c.history, graph=c.claim_graph,
                   claim_ids=c.prior_promise_claim_ids))
