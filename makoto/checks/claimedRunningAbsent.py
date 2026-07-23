from __future__ import annotations
from typing import Optional

from makoto.core.schema import Finding
from makoto.core.lexicons import (
    _RUNNING_CLAIM_RX, _PROCESS_START_VERB_RX, _PROCESS_LIFECYCLE_CMD_RX,
    _NEGATION_RX, _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.substrate.io import decode_history_row

# gate.claimed_running -- the assistant claims an ONGOING running/live/listening/serving state
# for a process/service ("the server is running", "it's up and running", "now listening on port
# 5173") but this session's OWN recorded Bash evidence contradicts it: either nothing
# process-shaped ever ran, or the most recently recorded process-start/liveness-check call ended
# in a direct error state. Same posture as gate.completion/gate.green_claim: a claim checked
# against makoto's own captured record, never against the live world -- makoto cannot itself go
# curl a port; it only re-reads what the agent's own tool calls already showed.
#
# AGNOSTIC in the same two senses this catalog already uses the word for gate.canon
# (canonTimeoutRecur.py's module docstring):
#   (1) the FAILURE verdict reads only protocol-level terminals -- `tool_response.interrupted`
#       and a non-zero `exitCode` -- no test-runner regex, no language/framework token;
#   (2) the command CLASSIFIER (_PROCESS_LIFECYCLE_CMD_RX) is a broad, open-world, multi-
#       ecosystem net (like _TEST_RUNNER_RX) -- an unlisted launcher/healthcheck shape is a
#       documented RECALL bound, never a false-block source.
#
# FP firewall: the claim itself only fires when a first-person process-lifecycle action verb
# (_PROCESS_START_VERB_RX: "I started/launched/ran/...") co-occurs anywhere in the same message --
# generic explanatory prose about how a tool behaves by default essentially never also narrates
# the assistant itself starting something, so this kills that FP class at a documented recall
# cost (a bare later re-confirmation with no start narrated in the same turn fails open).
#
# SCOPE (a named limitation, not a silent gap): evidence is Bash-only. A liveness confirmation
# the agent established some other way (a screenshot, a Read of a browser devtools log) is
# invisible here -- the same "open-world, textual-command" limitation is_test_runner documents
# for itself. Backgrounded launches (`cmd &`) almost always exit 0 at the SHELL level regardless
# of whether the backgrounded process itself later dies, so a clean exit is treated as fail-open
# silence, never as positive proof of liveness -- only a DIRECT error/interrupted state on the
# most recently recorded relevant call is treated as a contradiction.
#
# CROSS-AGENT EVIDENCE (2026-07-23): unlike every other gate, this one reads
# `ctx.history_all_agents` -- every agent-thread's PostToolUse Bash rows pooled, not narrowed to
# the calling thread by `_history_for_agent`. A subagent dispatched to start/verify a process is
# real session evidence the main thread's own claim must see; the thread-boundary firewall exists
# to stop a DANGLING (in-flight) PreToolUse from synthesizing a FAILURE across threads, a risk
# that does not apply to a completed PostToolUse Bash call. Residual, accepted risk: an unrelated
# subagent's unrelated process-lifecycle-shaped call failing could wrongly implicate this claim --
# narrower than the false positive this closes (a real launch invisible only because a different
# thread made it), not eliminated.
#
# NOT IN SCOPE (a documented limitation, not fixed here): both history views stay bounded by
# `_select_recent`'s 1-hour rolling window -- a launch more than an hour before the claim reads as
# "no evidence" (UNFULFILLED) even if the process is in fact still running. Same tradeoff class as
# the Bash-only/backgrounded-exit limits above; widening the window is a dispatch-wide change,
# out of this one gate's scope.


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
    """None iff no process-lifecycle-shaped Bash call (_PROCESS_LIFECYCLE_CMD_RX) ever ran this
    session -- the claim has zero grounding. Else True/False for whether the MOST RECENT such
    call ended in a direct agnostic error state: `interrupted`, or a recorded non-zero exit code
    -- the same two protocol terminals gate.canon reads (canonTimeoutRecur.py), no exit-code
    SEMANTICS guess beyond "non-zero", no language token. Latest-wins, like
    record.ledger.latest_testrun: a later clean re-check supersedes an earlier failed attempt."""
    verdict = None
    for cmd, tr in _bash_postuse_calls(history):
        if not _PROCESS_LIFECYCLE_CMD_RX.search(cmd):
            continue
        interrupted = tr.get("interrupted") is True
        exit_code = tr.get("exitCode", tr.get("exit"))
        verdict = bool(interrupted or (exit_code is not None and exit_code != 0))
    return verdict


def claimed_running_gate(text, *, history=()) -> Optional[Finding]:
    """Fire iff the assistant claims an ongoing running/live/listening/serving state
    (`_running_claim`) and this session's own recorded evidence contradicts it: no process-
    lifecycle Bash call ever ran (UNFULFILLED), or the most recently recorded one ended in a
    direct error state (MISREPORTED). Silent when the most recent such call was clean --
    fail-open: a clean exit is not proof of liveness (see module docstring's SCOPE note), but
    only a POSITIVE contradiction bites, never mere absence-of-proof-of-liveness."""
    if _running_claim(text) is None:
        return None
    failed = _latest_process_call_failed(history)
    if failed is None:
        return Finding(
            pattern_id="gate.claimed_running", file="", line=0, level="error",
            message=("Claim states a process/service is running, but no process-start or "
                      "liveness-check command appears anywhere in this session's recorded "
                      "history — the word must match the world."),
            retry_hint=("Actually start or verify the process with a real Bash call and cite a "
                        "clean result, or scope/retract the running claim."))
    if failed:
        return Finding(
            pattern_id="gate.claimed_running", file="", line=0, level="error",
            message=("Claim states a process/service is running, but the most recently recorded "
                      "process-start/liveness-check call ended in a direct error state "
                      "(interrupted, or a non-zero exit) — the word must match the world."),
            retry_hint=("Re-run the start/health-check to a real successful result and cite it, "
                        "or scope/retract the running claim."))
    return None


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.claimed_running", applies_at="Stop", posture="BLOCK", may_block=True,
               run=lambda c: claimed_running_gate(c.text, history=c.history_all_agents))
