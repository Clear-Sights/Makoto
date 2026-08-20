from __future__ import annotations
from typing import Optional

from makoto.vocab import Finding
from makoto.vocab import (
    _RUNNING_CLAIM_RX, _PROCESS_START_VERB_RX, _PROCESS_LIFECYCLE_CMD_RX,
    _NEGATION_RX, _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.kit import decode_history_event, failure_terminal_result

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
#   (1) the FAILURE verdict reads only protocol-level terminals -- `tool_response.interrupted`,
#       a non-zero `exitCode`, and PostToolUseFailure's top-level `error` -- no test-runner regex,
#       no language/framework token;
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
# `ctx.history_all_agents` -- every agent-thread's settled PostToolUse/PostToolUseFailure Bash
# rows pooled, not narrowed to the calling thread by `_history_for_agent`. A subagent dispatched
# to start/verify a process is real session evidence the main thread's own claim must see; the
# thread-boundary firewall exists to stop a DANGLING (in-flight) PreToolUse from synthesizing a
# FAILURE across threads, a risk that does not apply to a settled PostToolUse/PostToolUseFailure
# Bash terminal. Residual,
# accepted risk: an unrelated subagent's unrelated process-lifecycle-shaped call failing could
# wrongly implicate this claim -- narrower than the false positive this closes (a real launch
# invisible only because a different thread made it), not eliminated.
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
    in `text` OUTSIDE quoted/fenced spans (see module docstring) -- the firewall is span-filtered
    with the SAME _code_spans exclusion as the claim it guards, or a start verb merely QUOTED in
    a fence/backticks would arm the very gate _code_spans was added to disarm."""
    if not text:
        return None
    spans = _code_spans(text)
    if not any(not any(s <= m.start() < e for s, e in spans)
               for m in _PROCESS_START_VERB_RX.finditer(text)):
        return None
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
    """Yield (command, result_dict, is_failure_terminal) for every settled Bash terminal in
    `history`, in session order. A PostToolUseFailure's top-level error/is_interrupt fields become
    the same small result shape read below, while the boolean preserves where that error came
    from. Reuses the canonical row/event decode; a malformed row yields the (None, None, None)
    marker so the caller can fail OPEN on it -- silently dropping it would push the emptiness
    branch below toward BLOCK, the opposite of fail-open."""
    for row in history or ():
        ev = decode_history_event(row)
        if not isinstance(ev, dict):
            yield None, None, None
            continue
        event_type = ev.get("hook_event_name")
        # INCLUDE failed terminals: this gate distinguishes "no evidence" from "ran and failed".
        if event_type not in ("PostToolUse", "PostToolUseFailure"):
            continue
        if ev.get("tool_name") != "Bash":
            continue
        tool_input = ev.get("tool_input")
        cmd = str(tool_input.get("command", "") or "") if isinstance(tool_input, dict) else ""
        if event_type == "PostToolUseFailure":
            yield cmd, failure_terminal_result(ev), True
            continue
        tr = ev.get("tool_response")
        yield cmd, (tr if isinstance(tr, dict) else {}), False


def _latest_process_call_failed(history) -> Optional[bool]:
    """None iff no process-lifecycle-shaped Bash call (_PROCESS_LIFECYCLE_CMD_RX) ever ran this
    session -- the claim has zero grounding. Else True/False for whether the MOST RECENT such
    call ended in a direct agnostic error state: `interrupted`, a recorded non-zero exit code, or
    a PostToolUseFailure terminal -- protocol fields only, with no exit-code SEMANTICS guess
    beyond "non-zero" and no language token. The failure event type itself is sufficient evidence;
    its optional error text need not be present, and `failure_terminal_result` supplies generic
    text only so every decoder receives one stable shape. Latest-wins, like
    record.ledger.latest_testrun: a later clean re-check supersedes an earlier failed attempt.

    An UNDECODABLE history row makes the None ("no evidence") answer unassertable: the dropped
    row could be the very launch the claim cites, so absence of parseable evidence must not
    become a positive "no such command exists" -- with any undecodable row present and no
    decodable lifecycle verdict, this returns False (fail-open silence), never None."""
    verdict = None
    saw_undecodable = False
    for cmd, tr, is_failure_terminal in _bash_postuse_calls(history):
        if cmd is None:
            saw_undecodable = True
            continue
        if not _PROCESS_LIFECYCLE_CMD_RX.search(cmd):
            continue
        interrupted = tr.get("interrupted") is True
        exit_code = tr.get("exitCode", tr.get("exit"))
        verdict = bool(is_failure_terminal or interrupted
                       or (exit_code is not None and exit_code != 0))
    if verdict is None and saw_undecodable:
        return False
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
                     "liveness-check Bash command appears in this session's recent recorded "
                     "Bash history (the dispatcher's bounded event window) — the word must "
                     "match the world."),
            retry_hint=("Actually start or verify the process with a real Bash call and cite a "
                        "clean result, or scope/retract the running claim."),
        )
    if failed:
        return Finding(
            pattern_id="gate.claimed_running", file="", line=0, level="error",
            message=("Claim states a process/service is running, but the most recently recorded "
                     "process-start/liveness-check call ended in a direct error state "
                     "(interrupted, a non-zero exit, or a failed-tool error terminal) — the "
                     "word must match the world."),
            retry_hint=("Re-run the start/health-check to a real successful result and cite it, "
                        "or scope/retract the running claim."),
        )
    return None


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.claimed_running", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="CLAIM_VS_HISTORY",
               eats=frozenset({"text", "history_all_agents"}),
               run=lambda c: claimed_running_gate(c.text, history=c.history_all_agents))
