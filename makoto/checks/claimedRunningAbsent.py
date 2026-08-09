from __future__ import annotations
from typing import Optional

from makoto.core.schema import Finding
from makoto.core.lexicons import (
    _RUNNING_CLAIM_RX, _PROCESS_START_VERB_RX, _PROCESS_LIFECYCLE_CMD_RX,
    _NEGATION_RX, _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.substrate.io import decode_history_row
import makoto.substrate.claim_graph as _claim_graph

# gate.claimed_running -- an ongoing liveness claim is certified only by a successful recorded
# health observation for the same canonical endpoint/port. A clean launcher exit is a deed, not
# proof that a process remains live; a check of another port is unrelated. A failed exact-target
# check contradicts, and a later exact-target check supersedes only that predicate/target pair.
#
# FP firewall: the claim itself only fires when a first-person process-lifecycle action verb
# (_PROCESS_START_VERB_RX: "I started/launched/ran/...") co-occurs anywhere in the same message --
# generic explanatory prose about how a tool behaves by default essentially never also narrates
# the assistant itself starting something, so this kills that FP class at a documented recall
# cost (a bare later re-confirmation with no start narrated in the same turn fails open).
#
# SCOPE: health observations currently come from settled Bash probes recognized by the closed
# command classifier. Cross-agent observations are consumable only through an explicit,
# target-bound Agent/Task/Workflow delegation edge. Unnamed services remain NOT-EVALUABLE rather
# than borrowing identity from an unrelated lifecycle command.


def _running_claim(text: str):
    """Return the re.Match of a first-person, present-tense, ongoing process-liveness claim in
    `text`, else None. Mirrors substrate.claims.whole_suite_pass_claim's shape: closed-subject-
    head predicate, quoted/fenced spans excluded, a negated/forward-framed clause excluded (the
    window walks back to the last sentence boundary, so a leading 'once'/'when'/'if' anywhere in
    that same clause still voids the match). Requires a co-occurring first-person start verb
    ANYWHERE in `text` (see module docstring) -- checked first since it is the cheaper reject."""
    if not text or not _PROCESS_START_VERB_RX.search(text):
        return None
    spans = _code_spans(text)
    for m in _RUNNING_CLAIM_RX.finditer(text):
        a = m.start()
        if any(s <= a < e for s, e in spans):
            continue                                  # quoted/fenced -> not the agent's own prose claim
        clause = _SENTENCE_SPLIT_RX.split(text[max(0, a - 70):a])[-1]
        if _NEGATION_RX.search(clause) or _ADV_FORWARD_RX.search(clause):
            continue                                  # 'won't be running' / 'once deployed, it is running'
        return m
    return None


def _bash_postuse_calls(history):
    """Yield (command, tool_response_dict) for every PostToolUse Bash call in `history`, in
    session order. Reuses the one canonical row-decode step (substrate.io.decode_history_row);
    fail-open per row -- a malformed row is skipped, never raised."""
    for row in history or ():
        ev = decode_history_row(row)
        if not isinstance(ev, dict) or ev.get("hook_event_name") != "PostToolUse":
            continue
        if ev.get("tool_name") != "Bash":
            continue
        cmd = str((ev.get("tool_input") or {}).get("command", "") or "")
        tr = ev.get("tool_response")
        yield cmd, (tr if isinstance(tr, dict) else {})


def _latest_process_call_failed(history) -> Optional[bool]:
    """Legacy diagnostic for the former flat-history rule.

    None iff no process-lifecycle-shaped Bash call (_PROCESS_LIFECYCLE_CMD_RX) ever ran this
    session -- the claim has zero grounding. Else True/False for whether the MOST RECENT such
    call ended in a direct agnostic error state: `interrupted`, or a recorded non-zero exit code
    -- the same two protocol terminals gate.canon reads (canonTimeoutRecur.py), no exit-code
    SEMANTICS guess beyond "non-zero", no language token. Latest-wins, like
    record.ledger.latest_testrun. The gate itself uses target-typed graph observations."""
    verdict = None
    for cmd, tr in _bash_postuse_calls(history):
        if not _PROCESS_LIFECYCLE_CMD_RX.search(cmd):
            continue
        interrupted = tr.get("interrupted") is True
        exit_code = tr.get("exitCode", tr.get("exit"))
        verdict = bool(interrupted or (exit_code is not None and exit_code != 0))
    return verdict


def claimed_running_gate(text, *, history=(), graph=None, claim_ids=()) -> Optional[Finding]:
    """Reject running claims without target-identical liveness support."""
    if graph is None:
        graph, claim_ids = _claim_graph.build_ephemeral_graph(text, history=history)
    claims = [
        graph.claims[claim_id] for claim_id in claim_ids
        if claim_id in graph.claims and graph.claims[claim_id].predicate == "service.running"
    ]
    if not claims:
        return None
    for claim in claims:
        adjudication = graph.adjudicate(claim.node_id)
        if adjudication.verdict is _claim_graph.Verdict.CERTIFIED:
            continue
        if adjudication.verdict is _claim_graph.Verdict.CONTRADICTED:
            message = (
                f"Claim states {claim.target_value} is running, but the latest exact-target "
                "liveness observation failed."
            )
        else:
            message = (
                f"Claim states {claim.target_value} is running, but no target-identical liveness "
                "observation supports it — a launcher exit or a different port/service cannot "
                "certify ongoing liveness."
            )
        return Finding(
            pattern_id="gate.claimed_running", file="", line=0, level="error",
            message=message,
            retry_hint=("Re-run the start/health-check to a real successful result and cite it, "
                        "or scope/retract the running claim."))
    return None


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.claimed_running", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: claimed_running_gate(
                   c.text, history=c.history_all_agents, graph=c.claim_graph,
                   claim_ids=c.current_claim_ids))
