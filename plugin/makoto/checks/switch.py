from __future__ import annotations


from typing import Optional

from makoto.vocab import Finding
from makoto.vocab import (
    _RUNNING_CLAIM_RX, _PROCESS_START_VERB_RX, _PROCESS_LIFECYCLE_CMD_RX,
    _NEGATION_RX, _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX,
)
from makoto.substrate.claims import _code_spans
from makoto.kit import decode_history_event, failure_terminal_result, unwitnessed

# gate.claimed_running's SHAPE (see plugin/makoto/kit.py's `unwitnessed`): SWITCH -- the witness
# is a recorded act (a process-start/liveness-check Bash call) whose response was read.
running_SHAPE = "SWITCH"

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
# CROSS-AGENT EVIDENCE: unlike every other gate, this one reads
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

    None is reserved for the ONE case with no grounding at all: not a single settled Bash terminal
    in the window. Two other cases look like "no match" and are NOT-EVALUABLE, so both answer False
    (fail-open silence), never None:

      * an UNDECODABLE history row -- the dropped row could be the very launch the claim cites, so
        absence of parseable evidence must not become a positive "no such command exists";
      * Bash terminals exist but none matches `_PROCESS_LIFECYCLE_CMD_RX` -- the net is a closed
        vocabulary, so a real launcher outside it (`air`, `bun run dev`, `php artisan serve`,
        `caddy run`) is a RECALL MISS, not a contradiction. Firing there would tell an agent that
        genuinely started a server that no process-start command appears, which is a false block in
        the expensive direction. This is the same fail-open reasoning the undecodable row already
        gets, applied to the vocabulary as a whole rather than to one row.

    The fix is deliberately NOT "widen the net": a longer closed list is as monotone as a short
    one, and the next unlisted launcher would false-block identically."""
    verdict = None
    saw_undecodable = False
    saw_bash_terminal = False
    for cmd, tr, is_failure_terminal in _bash_postuse_calls(history):
        if cmd is None:
            saw_undecodable = True
            continue
        saw_bash_terminal = True
        if not _PROCESS_LIFECYCLE_CMD_RX.search(cmd):
            continue
        interrupted = tr.get("interrupted") is True
        exit_code = tr.get("exitCode", tr.get("exit"))
        verdict = bool(is_failure_terminal or interrupted
                       or (exit_code is not None and exit_code != 0))
    if verdict is None and (saw_undecodable or saw_bash_terminal):
        return False
    return verdict


def claimed_running_gate(text, *, history=()) -> Optional[Finding]:
    """Fire iff the assistant claims an ongoing running/live/listening/serving state
    (`_running_claim`) and this session's own recorded evidence contradicts it: no process-
    lifecycle Bash call ever ran (UNFULFILLED, `failed is None`), or the most recently recorded
    one ended in a direct error state (MISREPORTED, `failed is True`). Silent when the most
    recent such call was clean -- fail-open: a clean exit is not proof of liveness (see module
    docstring's SCOPE note), but only a POSITIVE contradiction bites, never mere
    absence-of-proof-of-liveness."""
    def owes(t):
        # The one subject a running claim commits to: itself. Cheap and pure -- the witness
        # (whether the session's own record contradicts it) lives in `paid`, below, so a claim
        # never even reaches that check once `_running_claim` alone rules it out.
        return (t,) if _running_claim(t) is not None else ()

    def pays(_t):
        return None

    for _ev, _claim in unwitnessed(
            (text,), owes=owes, pays=pays,
            paid=(lambda _t: _latest_process_call_failed(history) is False,)):
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
running_CHECK = _Check(id="gate.claimed_running", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="SWITCH",
               eats=frozenset({"text", "history_all_agents"}),
               run=lambda c: claimed_running_gate(c.text, history=c.history_all_agents))

import re

from makoto.kit import turn_tool_calls, unwitnessed

# gate.fabricated_action's SHAPE (see plugin/makoto/kit.py's `unwitnessed`): SWITCH -- the
# witness is a recorded act (any tool call this turn), not a re-reading of the claim itself.
action_SHAPE = "SWITCH"

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
# "I've/I'd deployed" is the same first-person completed-action claim as "I deployed" -- the
# contraction must not defeat the \bI\s+VERB shape (mirrors _PROCESS_START_VERB_RX's own
# contraction handling for the sibling gate.claimed_running).
_ACTION_RX = re.compile(rf"\bI(?:['’]ve|['’]d)?\s+{_ACTION_VERB}\s+(?P<obj>`[^`]+`|\S+)", re.I)
_NEG = re.compile(r"\b(?:not|never|without)\b|n't", re.I)
_FUTURE = re.compile(r"\b(?:will|going to|plan to|about to|let me)\b|i'?ll", re.I)
# PRIOR-TURN frame: the claim is a truthful RECAP of work done in an earlier turn/session, not an
# assertion that the action happened THIS (tool-less) turn. turn_tool_calls only counts THIS turn's
# calls (post-final-Stop), so a recap of last turn's real run reads as fabricated; this frame, scoped
# to the claim's own clause, fails open. GATE-LOCAL (turn_tool_calls in _shared.py is untouched).
_PRIOR_TURN = re.compile(
    r"\b(?:earlier|previously|already|before|last\s+turn|previous\s+turn|prior\s+turn|"
    r"this\s+session|in\s+the\s+last\s+turn|in\s+the\s+previous\s+turn|a\s+moment\s+ago)\b", re.I)


def _distinctive(obj: str) -> bool:
    """An object FP-safe enough to gate on: a backticked command, a path, or a URL. A bare prose
    word ('tests', 'X') is too FP-prone, so it is rejected (the agent must name a concrete target)."""
    if obj.startswith("`"):
        return True
    o = obj.strip("`'\".,;:)(")
    # a '.py' tail is already covered by the generic \.\w{2,4}$ extension test below (dedup)
    return bool("/" in o or o.startswith("http") or re.search(r"\.\w{2,4}$", o))


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
        # the verb). turn_tool_calls only sees THIS turn, so such a truthful recap reads as fabricated
        # -> fail open. The sentence is delimited cheaply on the surrounding terminators.
        s0 = max(text.rfind(p, 0, m.start()) for p in (". ", "! ", "? ", "\n")) + 1
        e1 = min((p for p in (text.find(". ", m.end()), text.find("\n", m.end())) if p != -1),
                 default=len(text))
        if _PRIOR_TURN.search(text[s0:e1 + 1]):
            continue                                  # recap of an earlier turn -> not this-turn claim
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
    def owes(t):
        # The one subject a fabricated-action claim commits to: the claimed object itself. Cheap
        # and pure -- the witness (any tool call this turn) lives in `paid`, below.
        obj = _action_signal(t)
        return (obj,) if obj is not None else ()

    def pays(_t):
        return None

    for _ev, obj in unwitnessed(
            (text,), owes=owes, pays=pays, paid=(lambda _o: turn_tool_calls(history) > 0,)):
        return Finding(
            pattern_id="gate.fabricated_action", file="", line=0, level="error",
            message=(f"Claim states a completed tool action ('{obj}'), but this turn made no tool calls "
                     f"at all — actually run it (any tool counts) and cite the result, or remove the claim."),
            retry_hint="Actually run the command/tool, or drop the claim that you did it.")
    return None


action_CHECK = _Check(id="gate.fabricated_action", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="SWITCH",
               eats=frozenset({"text", "history"}),
               run=lambda c: fabricated_action_gate(c.text, history=c.history))

# gate.unexamined_wall -- the agent says a thing cannot be known, having done nothing to find out.
#
# Register entry G5, WALL WITHOUT INVENTORY: "cannot" declared with the means already held; the
# fix line is "list what you hold before saying no". The entry has existed with no runner, which
# is entry B7 (a rule written and enforced nowhere) applied to G5. This is the runner.
#
# WHAT IT IS NOT. It does not judge whether a refusal was correct, and it does not read the
# operator's words. Its subject is the assistant's own statement held against the assistant's own
# act stream, which is the ordinary Makoto bar.
#
# THE COUNTABLE CORE, and why it is this and not something wider. "The means were held" is, in
# general, a question about whether some act would have answered the claim -- a similarity
# question, and similarity is judgement. There is one case where it is countable instead: an
# EPISTEMIC cannot -- a claim that something cannot be determined, told, checked or known --
# issued when the agent has taken NO act at all since the operator last spoke. Absence of the
# whole channel is countable in a way that "insufficient acts" never is, which is the same
# 0-FP construction `claimedConsentAbsent` rests on. A claim about what is knowable, made
# without a single act in the window, is a wall with the inventory unopened by construction.
#
# Two claim shapes are deliberately EXCLUDED because they are not epistemic and not falsifiable
# by acting: a refusal of a request ("I won't", "I can't help with"), and a statement of absent
# capability in the abstract ("models cannot browse"). Neither asserts that a fact about THIS
# work is unknowable, so neither is G5.
#
# THE WINDOW is the calls since the operator's last genuine turn (`last_operator_turn_ts` +
# `calls_since`), not the whole session, and the direction matters: over a whole session the
# "has acted" predicate is monotone, so one early call would silence the gate forever. Windowing
# asks the question G5 actually asks -- did you look BEFORE saying no, this time.
#
# STATED LIMITS, on the record rather than discovered later:
#
#   1. An agent that makes one unrelated call and then declares a wall is NOT caught. Relating
#      the call to the claim is the similarity question refused above.
#   2. G1 (goal substitution), G2 (determined asked as open) and G3 (scope below the answer) get
#      no runner here and none elsewhere. Each needs a comparison of the request against the
#      result, or of a question against what was derivable -- both similarity. They are named
#      here so their absence is a choice on the record. Measured against two real G2 incidents,
#      a zero-acts test catches neither, because in both the agent had acted extensively and
#      asked anyway; any honest G2 runner must compare the question to the read set, not count
#      acts.
from makoto.kit import unwitnessed

# gate.unexamined_wall's SHAPE (see plugin/makoto/kit.py's `unwitnessed`): SWITCH -- the witness
# is a recorded act (any call since the operator's last turn), not a re-reading of the claim
# itself.
wall_SHAPE = "SWITCH"

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

wall_RETRY_HINT = ("You state that something cannot be determined, but you have taken no action since "
              "the operator last spoke. List what you hold and act on it first; if the claim "
              "survives the attempt, say what you tried and what it returned.")
wall_DESCRIPTION = ("Blocks a claim that something cannot be determined when the agent has taken no "
               "action at all since the operator's last turn.")


def wall_owes(text):
    """The one subject a wall claim commits to: itself. Cheap and pure -- the witness (an act
    taken since the operator's last turn) lives in `paid`, below."""
    return (m,) if (m := _WALL_RX.search(text or "")) else ()


def wall_pays(_text):
    return None


def _act_window_paid(history, transcript_path) -> bool:
    """True (silent) unless the act window since the operator's last turn is CONFIRMED both
    establishable and empty. Never raises: every failure to establish the window reads as NO
    EVIDENCE and pays silently, because the alternative -- blocking a turn on a decode failure --
    is a gate resting on a false fact. Note the asymmetry that keeps that safe: `calls_since`
    widens the window when the boundary cannot be read, so an unreadable transcript yields MORE
    calls, never fewer, and this only pays False (fires) on a confirmed zero."""
    from makoto.state.ledger import last_operator_turn_ts
    from makoto.substrate._canonAtoms import calls_since
    try:
        since = last_operator_turn_ts(transcript_path)
    except Exception:
        return True
    if since is None:
        # No operator turn to window against. The claim may still be a wall, but the question
        # this gate asks -- did you look before saying no, THIS time -- has no boundary, and a
        # window that cannot be established must never widen what is blocked.
        return True
    try:
        acts = calls_since(history, since)
    except Exception:
        return True
    return bool(acts)


def unexamined_wall_gate(text, *, history=None, transcript_path=None):
    """One BLOCKING Finding when an epistemic cannot is stated with a confirmed-empty act
    window."""
    for _ev, wall in unwitnessed(
            (text,), owes=wall_owes, pays=wall_pays,
            paid=(lambda _w: _act_window_paid(history, transcript_path),)):
        return Finding(
            pattern_id="gate.unexamined_wall",
            file="", line=0, level="error",
            message=(f"Claim that a fact cannot be established ({wall.group(0)!r}), with no action "
                     f"taken since the operator last spoke — the inventory was never opened."),
            retry_hint=wall_RETRY_HINT,
        )
    return None


wall_CHECK = _Check(id="gate.unexamined_wall", applies_at="Stop", posture="BLOCK",
               may_block=True, tests="SWITCH",
               keywords=("no way to tell", "no way to know", "cannot determine",
                         "can't tell", "no way of knowing", "unable to verify"),
               retry_hint=wall_RETRY_HINT, description=wall_DESCRIPTION,
               eats=frozenset({"text", "history", "transcript_path"}),
               run=lambda c: unexamined_wall_gate(c.text, history=c.history,
                                                  transcript_path=c.transcript_path))

# The engine half (primitives + the history->Call adapter) is PURE stdlib (json/dataclasses/
# typing/__future__), no makoto import at all, so the gate-shape import firewall
# (tests/test_import_direction.py) is satisfied by construction; the adapter half below
# (`canon_gate`/`CHECK`) is what imports `makoto.vocab`/`makoto.context`.
#
# A primitive here reads the closed agnostic terminal set: {tool_name, tool_input identity,
# interrupted, self_error_code}. No language- or test-runner-specific regex appears. `canon.recur`
# also uses `kit.classify_failure` over the host-emitted error text only to budget confidently
# transient failures; its markers are generic failure vocabulary, never runner or language tokens.
# Two primitives are installed:
#
#   * canon.timeout — `timed_out_at_turn_end`: the turn closed with the LAST decoded call in a
#     direct error state (interrupted or a self-emitted error code) — NOT "any call errored
#     somewhere", because a resolved-then-fixed error must stay silent. One confidently transient,
#     non-interrupted failure is also silent; an explicit harness interruption and deterministic or
#     uncertain errors retain the one-call bar.
#   * canon.recur   — `recur_stuck`: the SAME tool call (identical tool_name + byte-identical
#     tool_input) re-issued in a CONSECUTIVE run of length >=2 where EVERY call in that run is in
#     a direct error state — a stuck retry loop with nothing changed between attempts. A run of
#     confidently transient failures gets one extra re-poll: it becomes stuck only after that key
#     has accumulated three transient failures across the stream, reset by that key's success;
#     deterministic and uncertain failures keep the two-call bar. Verdict is judged per KEY at the
#     END of each maximal consecutive run, and the LAST judgment for each key wins — so a later
#     success for the same key silences it even when other, different calls happened in between.
#
# PATTERN_ID CONVENTION: `dispatch._blocking_gate_ids()` derives the blocking set from
# `{c.id for c in load_checks(edge="Stop") if c.may_block and c.posture == BLOCK}` — the CHECK's
# OWN id ("gate.canon") — and filters gate_findings by `finding.pattern_id in
# _blocking_gate_ids()`. Every other live gate stamps `pattern_id == its own CHECK id`, so a
# per-primitive pattern_id here would make `canon.timeout`/`canon.recur` findings silently
# invisible to `_blocking_gate_ids()` — discovered but never actually blocking. This stamps
# `pattern_id="gate.canon"` instead and keeps the firing sub-primitive's identity in the MESSAGE,
# prefixed `"canon.<id>: "`.
#
# LEVEL: "error" — the ONLY blocking level in live makoto (makoto.vocab._ALLOWED_FIRE_LEVELS ==
# {"error"}). This is an ORDINARY blocking gate, NOT the one advisory exception
# `gate.self_wired` uses.
#
# IMPORT FIREWALL (tests/test_gate_shape.py::test_no_gate_module_imports_a_sibling_or_cross_l2):
# imports ONLY makoto.vocab, makoto.context, and the pure primitives below.
import json
import os
from typing import Iterable, List

from makoto.kit import (canon_input, classify_failure, decode_history_event,
                        failure_terminal_result, unwitnessed)

# SHAPE = SWITCH: both primitives below judge a recorded act that exercised the thing -- a tool
# call whose response was read (`timed_out`/`self_error_code`) -- never a second independent
# source or a read of source material.
canon_SHAPE = "SWITCH"

# A Call is one paired tool event in protocol form: {"name": tool_name, "input": tool_input,
# "result": tool_response} — tool_input/tool_response are kept as full DICTS (not the flattened
# strings makoto.kit.iter_tool_events produces) since the terminals below need real dict
# lookups (`result.get("interrupted")`, `result.get("error")`).
Call = dict


# ---- agnostic terminals: each reads ONE protocol field, no language token --------------------
def _result(c: Call) -> dict:
    r = c.get("result")
    return r if isinstance(r, dict) else {}


def _input(c: Call) -> dict:
    i = c.get("input")
    return i if isinstance(i, dict) else {}


def interrupted(c: Call) -> bool:
    """agnostic terminal `interrupted`: the harness set result.interrupted True (timeout/abort)."""
    return _result(c).get("interrupted") is True


def exit_code(c: Call):
    """agnostic terminal `exit_code`: the recorded process exit code, or None if absent. Kept as
    a terminal helper for any future primitive that needs it; `timed_out` deliberately does not
    read it (see its own docstring — the real substrate carries no exit_code on tool calls, and a
    non-zero exit on an idempotent call is not itself an error state).

    The key read is the real substrate's camelCase `"exitCode"`, matching every other reader of a
    Bash tool_response in this repo."""
    return _result(c).get("exitCode")


def self_error_code(c: Call):
    """agnostic terminal `self_error_code`: a harness-emitted error code/object on the result.
    PRESENCE-based for the `error` field: a present, non-None `error` — even a falsy one such
    as `""` — is a self-reported error state. `error_code` keeps the truthy requirement: `0` is
    the conventional success code, not an error."""
    r = _result(c)
    if "error" in r and r["error"] is not None:
        return r["error"]
    return r.get("error_code") or None


def stale_read_hint(c: Call):
    """agnostic terminal `stale_read_hint`: the harness's own stale-read-state warning on the
    result, read verbatim (string/dict/whatever shape the harness emits, or None if absent).
    Maps to the real substrate's `tool_response.staleReadFileStateHint` (the terminal's `result`
    IS the raw tool_response dict passed through in full by `calls_from_history`, so this is a
    plain key lookup, not a new decode step). Observability-only: no primitive reads it yet."""
    return _result(c).get("staleReadFileStateHint")


def sandbox_bypassed(c: Call) -> bool:
    """agnostic terminal `sandbox_bypassed`: True iff the call's own tool_input requested the
    sandbox-bypass escape hatch. Reads `input.dangerouslyDisableSandbox`, a real tool_input schema
    key, not a guessed name. Absence (the overwhelmingly common case) returns False, never
    crashes. Observability-only: no primitive reads it yet."""
    return _input(c).get("dangerouslyDisableSandbox") is True


# ---- the installed per-call primitive (type-2, direct error state) ---------------------------
def timed_out(c: Call) -> bool:
    """A direct, language-agnostic error state: the call was interrupted OR carried a self-emitted
    error code. Reads only agnostic terminals — no test-runner regex, no exit_code (a non-zero
    exit on an idempotent call, e.g. two identical `grep -r TODO` returning exit 1 / no-match, is
    normal, not a timeout — exit_code buys no true positive here and costs false ones). Presence
    test (`is not None`), not truthiness: `self_error_code` reports a present-but-falsy `error`
    field as `""`, which is still an error state (see its docstring)."""
    return interrupted(c) or self_error_code(c) is not None


# ---- sequence-aware primitives (read a span of the call stream, not one call) ----------------
def recur_stuck(calls: list) -> bool:
    """RECUR / non-refire: a STUCK RETRY LOOP. Fires iff, for at least one (tool_name,
    tool_input) key, that key's MOST RECENT maximal consecutive run (no intervening *different*
    call) in the call stream has length >= 2 and every call in it is in a direct error state
    (`timed_out`). A run made entirely of confidently transient failures needs the same
    consecutive run length plus at least three transient failures for that key across the stream;
    a success for that key resets its transient count. Deterministic and uncertain errors keep
    the ordinary two-call threshold.

    Deliberately conservative: silent if any retry changed the input (real progress), if any
    different action intervened (loop broken) with nothing further from that same key, or if any
    occurrence in the run succeeded (no error state). Each key's verdict is DEFERRED to the END
    of each maximal consecutive run for that key (run boundary or end of list): a run is judged
    bad only when it ends with run_len>=2 and every call in it was in the no-info error state. So
    [ERR, ERR, OK] does NOT fire — the later identical SUCCESS lands in the same run and flips
    run_all_err False before the run ends, silencing the loop.

    A key whose retries eventually succeed, however many unrelated calls sit in between, is not a
    stuck loop by the time the turn ends — only a key whose MOST RECENT run is itself still bad
    fires. Every run is judged as it closes, per key, and the LAST judgment for each key wins; a
    fresh success (even a lone one, not itself part of a run>=2) for a key overwrites an earlier
    bad verdict for that same key and resets its transient budget."""
    def _run_is_bad(key, length, all_err, all_transient) -> bool:
        if length < 2 or not all_err:
            return False
        return not all_transient or transient_failures.get(key, 0) >= 3

    last_bad: dict = {}     # key -> whether that key's most-recently-closed run was stuck-bad
    transient_failures: dict = {}  # key -> transient failures since that key's latest success
    run_key = None          # (name, canonical_input) of the current consecutive identical run
    run_all_err = False     # every call in the current run so far was in a no-info error state
    run_all_transient = False  # every call in the current run is a confidently transient error
    run_len = 0
    for c in calls or ():
        # Dunder-insensitive verdict identity (`_pairing_input`, like the Pre<->Post pairing): a
        # harness bookkeeping key that VARIES per call (`__seq`) would split a byte-identical
        # retry loop into distinct keys, so recur would never see a run of length >= 2. A leading
        # `__` is transport bookkeeping, never call semantics, so folding it cannot collapse two
        # genuinely distinct calls (the same argument as for pairing).
        key = (c.get("name", ""), _pairing_input(c.get("input")))
        call_err = timed_out(c)          # the same direct-error-state terminal the gate installs
        error = self_error_code(c)
        # a confidently transient, self-reported failure is budgeted, not counted as stuck yet
        call_transient = (call_err and error is not None
                          and classify_failure(str(error)) is False)
        if not call_err:
            transient_failures[key] = 0
        elif call_transient:
            transient_failures[key] = transient_failures.get(key, 0) + 1
        if key == run_key:
            run_len += 1
            run_all_err = run_all_err and call_err
            run_all_transient = run_all_transient and call_transient
        else:
            # the previous run just ENDED — judge it now that it's complete
            if run_key is not None:
                last_bad[run_key] = _run_is_bad(
                    run_key, run_len, run_all_err, run_all_transient)
            run_key = key
            run_len = 1
            run_all_err = call_err
            run_all_transient = call_transient
    # judge the final run at end-of-list
    if run_key is not None:
        last_bad[run_key] = _run_is_bad(
            run_key, run_len, run_all_err, run_all_transient)
    for _ev, _key in unwitnessed(last_bad.items(), owes=recur_owes, pays=recur_pays):
        return True
    return False


# `item` is `(key, is_bad)` -- one key's LAST-closed run judgment (`_run_is_bad`, above). A key
# whose latest run closed bad owes a witness that it is not, in fact, a stuck loop; a key whose
# latest run closed clean owes nothing -- a fresh success already discharged it before this gate
# runs (the "latest judgment wins" rule the module docstring documents). One-line by construction
# (module-level lambda, not `def`): the design pins this module's top-level function COUNT, and
# `_run_is_bad` above has already folded every later success into each key's one verdict, so there
# is no loop left for this step to do.
recur_owes = lambda item: (item[0],) if item[1] else ()
# No witness pays a stuck-loop verdict here: by the time an item reaches `recur_owes` there is
# nothing left that could still discharge it (see `recur_owes`'s own comment).
recur_pays = lambda _item: None


# The harness's own timeout wording ("Command timed out after 2m 0.0s"). Generic failure
# vocabulary, not a runner or language token — the same tier as `kit.classify_failure`'s own
# markers. Needed because classify_failure files ALL timeout text under its transient class,
# which made canon.timeout silent on the exact condition it is named for.
_TIMEOUT_TEXT_RX = re.compile(r"\btimed?\s?out\b", re.IGNORECASE)


def timed_out_at_turn_end(calls: list) -> bool:
    """canon.timeout: the turn CLOSED on an UNRESOLVED direct error — the LAST decoded call before
    Stop is in a direct error state (`timed_out`: interrupted or self_error_code).

    Sequence-level, NOT per-call EXISTS: the signal is "left unresolved AT TURN-END", not "an
    error occurred somewhere in the turn". A call that errored but was RESOLVED before the turn
    closed — a later call succeeded, e.g. a flaky command re-run that finally passed — is not a
    silent unresolved error, so it stays silent. An explicit harness interruption still fires
    even when its accompanying text sounds transient, and so does an error whose text carries
    the harness's own TIMEOUT wording (`_TIMEOUT_TEXT_RX`): classify_failure files all timeout
    text under its transient class, and letting that silence THIS primitive made canon.timeout
    silent on the very condition it is named for. Deterministic and uncertain errors retain the
    ordinary one-call bar. A confidently transient, non-interrupted failure is a recoverable
    blip with ONE retry opportunity — the budget the stop_text has always asserted: the FIRST
    transient failure of a key at turn end stays silent, but a key that has accumulated two or
    more transient failures since its last success (identical calls, however many unrelated
    calls sit between them — the non-consecutive gap recur's three-strike budget cannot see)
    has used its retry opportunity, and a turn still closing on that same failing key fires."""
    if not calls:
        return False
    last = calls[-1]

    def _timeout_forgiven(call: dict) -> bool:
        """True iff the turn's unresolved-looking close on `call` is actually forgiven: an
        explicit interruption or the harness's own timeout wording is NEVER forgiven, an error
        classified as anything but confidently transient is never forgiven, and a confidently
        transient error is forgiven only while its key's transient budget (< 2 across `calls`,
        this call included) is not yet exhausted. Exact mirror of this function's own old inline
        body -- see the module docstring for the budget's rationale. Nested here (not top-level):
        the design pins this module's top-level function count, and `calls` is this closure's
        only reason to exist as more than a one-line lambda."""
        if interrupted(call):
            return False
        error = self_error_code(call)
        if error is None:
            return False  # unreachable when `timed_out(call)` is True, kept for body parity
        text = str(error)
        if _TIMEOUT_TEXT_RX.search(text):
            return False
        if classify_failure(text) is not False:
            return False
        # confidently transient: budget the escape (one retry opportunity, per the stop_text).
        key = (call.get("name", ""), _pairing_input(call.get("input")))
        transients = 0
        for c in calls:
            if (c.get("name", ""), _pairing_input(c.get("input"))) != key:
                continue
            if not timed_out(c):
                transients = 0                # this key's success resets its budget
                continue
            e = self_error_code(c)
            if e is not None and classify_failure(str(e)) is False:
                transients += 1
        return transients < 2

    for _ev, _subject in unwitnessed(
            (last,), owes=timeout_owes, pays=timeout_pays,
            paid=(_timeout_forgiven,)):
        return True
    return False


# The last call in the stream owes a witness that the turn did not close on it unresolved -- only
# when it is itself in a direct error state (`timed_out`); a last call that succeeded owes
# nothing, so `_timeout_forgiven`'s transient-budget question never even needs asking. One-line by
# construction (module-level lambda, not `def`): see `recur_owes`'s comment for why.
timeout_owes = lambda call: (call,) if timed_out(call) else ()
# The only witness `timed_out_at_turn_end` reads is the seeded budget check in `paid`
# (`_timeout_forgiven`, nested there), not a second event -- there is exactly one call to judge
# (the LAST one), so nothing here ever adds a fresh witness.
timeout_pays = lambda _call: None


def _pairing_input(inp) -> str:
    """`canon_input` with leading-dunder keys dropped — the call-identity fold used to pair a
    PostToolUse back to its own PreToolUse AND as the per-key
    verdict identity inside this module's own sequence primitives (`recur_stuck`,
    `timed_out_at_turn_end`'s transient budget).

    A harness may add bookkeeping keys to `tool_input` BETWEEN a call's Pre and its Post, so
    pairing on the FULL canonical input would leave a dangling Pre for a call that in fact
    succeeded. The same holds for verdict identity: a bookkeeping key that VARIES per call
    (`__seq`) would split a byte-identical retry loop into distinct keys, hiding a run of length
    >= 2 from `recur_stuck`.

    A leading `__` is a transport/bookkeeping convention, never call semantics, so dropping it
    cannot collapse two genuinely distinct calls — for pairing or for a verdict. Primitives in
    OTHER modules (`identical_retry`) still key on their own folds.

    String leaves are also stripped of leading/trailing whitespace before folding: a retry whose
    command differs only by incidental surrounding whitespace ("flaky-tool --check " vs
    "flaky-tool --check") is the SAME call for verdict/pairing purposes, and treating it as a
    distinct key would let a genuinely stuck retry loop escape `recur_stuck`/the transient budget
    by accumulating one stray space per attempt."""
    return canon_input(_strip_leaves(_drop_dunders(inp)))


def _drop_dunders(inp):
    if isinstance(inp, dict):
        return {k: v for k, v in inp.items() if not str(k).startswith("__")}
    return inp


def _strip_leaves(v):
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return {k: _strip_leaves(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_strip_leaves(x) for x in v]
    return v


# ---- the history -> Call adapter (protocol-field decode; fail-open per row) -------------------
def _decode_row(row):
    """Decode ONE history row into (etype, name, input_dict, result_dict), or None to skip.

    Raw decode + wrapper-event-type fallback is `kit.decode_history_event` -- the canonical
    step, shared with `identicalRetryInterdiction._most_recent_completed_bash_call`. This
    function keeps only what's specific to canon's OWN adapter shape: the tuple conversion, and
    PostToolUseFailure normalized to PostToolUse with its real top-level error/is_interrupt
    fields, so it is the failed call's terminal. PreToolUse rows decode too; `calls_from_history`
    yields nothing for them."""
    ev = decode_history_event(row)
    if ev is None:
        return None
    etype = ev.get("hook_event_name")
    name = ev.get("tool_name", "") or ""
    if etype not in ("PreToolUse", "PostToolUse", "PostToolUseFailure") or not name:
        return None
    ti = ev.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    if etype == "PostToolUseFailure":
        return ("PostToolUse", name, ti, failure_terminal_result(ev))
    if etype == "PostToolUse":
        tr = ev.get("tool_response")
        return ("PostToolUse", name, ti, tr if isinstance(tr, dict) else {})
    return ("PreToolUse", name, ti, {})


def calls_from_history(history) -> list:
    """Every terminal row (PostToolUse, or PostToolUseFailure normalized to it by `_decode_row`)
    is one Call; a PreToolUse row is not a call and yields nothing. A call the owner declined,
    one that was abandoned, and one still running all leave the same trace, a Pre with no
    terminal, and none of them is evidence of a failure."""
    return [{"name": name, "input": ti, "result": tr} for etype, name, ti, tr in (d for d in (_decode_row(r) for r in (history or ())) if d is not None) if etype == "PostToolUse"]


# ---- sequence-primitive catalog: {id -> (seq_predicate(calls)->bool, stop_text, retry_hint)} --
# Each predicate reads the WHOLE decoded call list because its signal is a pattern across the
# stream. side=NEG, when=DETECTIVE. The ADAPTER below stamps every resulting Finding
# pattern_id="gate.canon" (matching live makoto's one-pattern-id-per-gate convention) and names
# the firing sub-primitive ("canon.<id>") at the front of the Finding's message instead — see the
# module docstring for why.
CANON_SEQ_PRIMITIVES: dict = {
    "timeout": (
        timed_out_at_turn_end,
        "A tool call ended in a direct error state — interrupted or a self-emitted error code — "
        "and the turn closed without resurfacing or resolving it; confidently transient, "
        "non-interrupted failures receive one retry opportunity.",
        "A call errored (timeout / interrupted / error code) and the turn closed without "
        "resolving it. Re-run it (or the equivalent action) to a real successful result before "
        "closing. Text alone cannot discharge this any other way; the detector reads only "
        "whether the LAST call in the turn succeeded.",
    ),
    "recur": (
        recur_stuck,
        "The same tool call was re-issued back-to-back with an identical input and kept ending in "
        "the same direct error state — a stuck retry loop with nothing changed between attempts.",
        "You retried the byte-identical failing call with no intervening change. Change the input, "
        "fix the underlying cause, or take a different action before re-running — re-issuing the "
        "same failing call unchanged cannot make progress.",
    ),
}


def fired_primitives(history) -> Iterable:
    """Yield (canon_id, stop_text, retry_hint) for every installed primitive that fires on the
    session's call stream. Pure: no makoto import, no I/O beyond decoding the passed-in history
    rows."""
    calls = calls_from_history(history)
    for cid, (seq_pred, stop_text, retry_hint) in CANON_SEQ_PRIMITIVES.items():
        if seq_pred(calls):
            yield (cid, stop_text, retry_hint)


def canon_gate(history, *, transcript_path=None, session_id=None, state_root=None) -> List[Finding]:
    """Fire one BLOCKING Finding per agnostic Canon primitive that matches the call stream, each
    stamped pattern_id="gate.canon" (so it actually blocks — see the module docstring's
    PATTERN_ID CONVENTION note) with the sub-primitive named at the front of its message
    ("canon.timeout: ..." / "canon.recur: ..."). Returns [] (silent) when no installed primitive
    fires — the discriminator's true-negative path.

    Both primitives read the same operator window as the fingerprint gate. A new genuine
    message or explicit host user-interruption closes the old window; a later error is still
    evaluated normally. Generic timeout/abort results do not establish operator intent.

    """
    try:
        import makoto.state.ledger as _ledger
        history = _ledger.operator_window(history, transcript_path)
    except Exception:
        pass
    out: List[Finding] = []
    for cid, stop_text, retry_hint in fired_primitives(history):
        out.append(Finding(
            pattern_id="gate.canon",
            file="",
            line=0,
            level="error",
            message=f"canon.{cid}: {stop_text}",
            retry_hint=retry_hint,
        ))
    return out


canon_CHECK = _Check(id="gate.canon", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="SWITCH",
               eats=frozenset({"history", "transcript_path", "session_id", "state_root"}),
               run=lambda c: canon_gate(c.history, transcript_path=c.transcript_path,
                                         session_id=c.session_id, state_root=c.state_root))

# makoto.checks.identicalRetryInterdiction -- D1 (docs/DEFERRED.md): PreToolUse interdiction of
# a byte-identical Bash retry immediately following a DETERMINISTIC failure of the SAME call --
# "kills the loop at length 1," the PROACTIVE twin of canon.recur (canonTimeoutRecur.py, which is
# reactive at Stop, judging a run of >=2 consecutive identical failing calls after the fact). This
# fires BEFORE the redundant call even runs.
#
# Ship bar (two design consultations, docs/DEFERRED.md D1): BLOCK-tier only, and ONLY when
# `_failureClassifier.classify_failure` returns a CONFIDENT True (deterministic) for the prior
# call's result -- never on a transient failure (a timeout, a 5xx, "still running"), and never on
# an uncertain classification. An advisory version was rejected outright (this project's own
# deliberate warning-tier-elimination invariant: "a hedge that emits a finding nobody acts on" is
# the exact illusory-word shape Makoto exists to catch); a block with a KNOWN transient-retry FP
# class would fail the SAME zero-FP admissibility bar the invariant demands. This predicate fires
# ONLY on the confident-True side of that bar.
#
# "No intervening state change" is enforced structurally, not by scanning for one: only the
# SINGLE MOST RECENT history row is consulted. If anything else happened between the failing call
# and now (a different tool call, a file edit, another Bash command), THAT would be the most
# recent row instead, and this predicate stays silent -- an intervening action always breaks the
# match by construction.
from makoto.kit import (bash_output_text, canon_input, classify_failure, decode_history_event,
                        failure_terminal_result, unwitnessed)
from makoto.registry import Check

# The witness is the SINGLE MOST RECENT recorded act that exercised the same command -- a Bash
# call whose response was already read -- never a second, independent source.
retry_SHAPE = "SWITCH"


def retry_owes(ev):
    """The about-to-run CURRENT Bash call owes a witness that it is not a byte-identical retry
    of the immediately preceding call. `ev` is `("current", (prior_input, current_input))`; any
    other kind owes nothing. Embeds the canon_input equality test itself (like `canon_gate`'s own
    primitives), so a call whose input differs from the prior one never even raises the
    obligation -- there is nothing to interdict."""
    kind, payload = ev
    if kind != "current":
        return ()
    prior_input, current_input = payload
    if canon_input(prior_input) != canon_input(current_input):
        return ()
    return (canon_input(current_input),)


def retry_pays(ev):
    """The PRIOR call's own recorded response is the only witness this predicate reads. `ev` is
    `("prior", prior_result_text)`; any other kind pays nothing. It pays the retry unconditionally
    whenever the prior call's classification is anything other than a confident deterministic
    failure (transient or uncertain both legitimize retrying) -- a confident deterministic failure
    pays nothing, leaving the identical retry owed."""
    kind, payload = ev
    if kind != "prior":
        return None
    if classify_failure(payload) is not True:
        return lambda _subject: True
    return None


def _most_recent_completed_bash_call(history) -> Optional[tuple]:
    """(tool_input, result_text) of the SINGLE MOST RECENT history row, iff that row is a
    settled PostToolUse/PostToolUseFailure Bash call -- else None (a different tool, a Pre row,
    or nothing at all). Failed terminals classify their real top-level error text.

    Decoding is `kit.decode_history_event` -- the canonical row-decode-plus-wrapper-fallback
    step, shared with `canonTimeoutRecur._decode_row`. Sharing it is what keeps this predicate
    and its sibling gate (canon.timeout/canon.recur) reading the SAME rows from the same table
    for the same concept -- including rows whose event type lives only on the WRAPPER column."""
    rows = list(history or ())
    if not rows:
        return None
    ev = decode_history_event(rows[-1])
    if ev is None or ev.get("tool_name") != "Bash":
        return None
    event_type = ev.get("hook_event_name")
    # INCLUDE failed terminals: this check reasons about the immediately prior failed attempt.
    if event_type not in ("PostToolUse", "PostToolUseFailure"):
        return None
    ti = ev.get("tool_input") or {}
    if event_type == "PostToolUseFailure":
        return ti, failure_terminal_result(ev)["error"]
    tr = ev.get("tool_response") or {}
    if isinstance(tr, dict):
        # A RECORDED zero exit is a call that SUCCEEDED: there is no failure to interdict,
        # whatever failure-shaped PHRASES its output happens to carry (e.g. grepping logs for
        # "No such file or directory" puts the marker in stdout of a passing call). Only an
        # explicitly recorded 0 short-circuits; an absent exit code still defers to
        # `classify_failure` over the output text, exactly as before.
        recorded_exit = tr.get("exitCode", tr.get("exit"))
        if recorded_exit == 0 and not isinstance(recorded_exit, bool):
            return None
    text = bash_output_text(tr) if isinstance(tr, dict) else str(tr)
    return ti, text


def retry_predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    if current_event.get("tool_name") != "Bash":
        return None
    prior = _most_recent_completed_bash_call(history)
    if prior is None:
        return None
    prior_input, prior_result_text = prior
    current_input = current_event.get("tool_input") or {}
    events = (("prior", prior_result_text), ("current", (prior_input, current_input)))
    for _ev, _subject in unwitnessed(events, owes=retry_owes, pays=retry_pays):
        return Finding(
            pattern_id=pattern.id,
            file="",
            line=0,
            level="error",  # Pre-tier is invariantly BLOCK; Check has no fire_level (test_pre_tier_block_invariant.py)
            message=("Identical retry of a Bash call that just failed deterministically -- retrying "
                     "the byte-identical command cannot change a deterministic error."),
            retry_hint=pattern.retry_hint,
        )
    return None


retry_RETRY_HINT = 'You retried the byte-identical failing Bash command with no intervening change, and the prior failure was deterministic (a syntax/import/permission/not-found error) -- retrying it unmodified cannot make progress. Change the command, fix the underlying cause, or take a different action.'
retry_DESCRIPTION = "byte-identical Bash retry immediately following that SAME call's deterministic failure -- no intervening state change"

retry_CHECK = Check(id="event.identical_retry", applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('Bash',), retry_hint=retry_RETRY_HINT, description=retry_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern"}), tests="SWITCH")

from makoto.vocab import _SENTENCE_SPLIT_RX
# Re-exported here, not duplicated, because this module's own tests and tests/test_lexicons.py
# address them under these names -- one home, two spellings, never two copies.
from makoto.vocab import (_TESTNAME_RX, _TEST_ID, _REC_FAIL_LEAD_RX, _REC_FAIL_TRAIL_RX,
                          _REC_PASS_LEAD_RX, _REC_PASS_TRAIL_RX, _TEETH_SCOPE_BEFORE,
                          _TEETH_SCOPE_AFTER, _recorded_names, recorded_failed_names,
                          recorded_passed_names)
from makoto.kit import current_named_verdicts, unwitnessed

# SHAPE = OTHER_POINT: the witness is a second reading of the SAME subject -- the named test's
# own current recorded verdict (`current_named_verdicts`, folded from history rows), never an act
# exercised here or a read of source.
named_SHAPE = "OTHER_POINT"


# Every exact test name `text` claims is PRESENTLY passing commits to that claim being true --
# see `claimed_passing_names` for what qualifies as a clean, present-tense, unnegated claim
# naming that exact identifier. No event here pays a named claim directly: the witness is seeded
# once, in `paid`, from the RECORD's own current verdict for that name (`_family_grounded`,
# nested inside `named_test_gate`) -- a second reading of the same subject, not a fresh event in
# this stream. Both one-line by construction (module-level lambdas, not `def`): the design pins
# this module's top-level function count at 3 (`_external_pass_predicate`,
# `claimed_passing_names`, `named_test_gate`).
named_owes = lambda text: sorted(claimed_passing_names(text))
named_pays = lambda _text: None

# gate.named_test — a NAMED-test pass-claim contradicted by that test's recorded FAILURE.
#
# The gate.green_claim DELTA. green_claim fires on a WHOLE-SUITE claim ("tests pass", "the suite is
# green") and DELIBERATELY firewalls to a universal subject — a named or subset claim fails open. This
# gate covers exactly that orthogonal slice: a claim that a SPECIFIC NAMED test passes ("`test_foo`
# passes", "test_bar is green"). A named test is coreference-PINNED, so the contradiction is precise:
#
#     a named-test pass-claim   ✗   a recorded FAILURE of THAT SAME named test, UNRESOLVED.
#
# Distinct from green_claim on every axis: SUBJECT is an exact test_\w+ id (not a universal suite
# head); the PIN is exact-name coreference (test_foo != test_foobar); the EVIDENCE is a per-test
# FAILED line for THAT name (not is_failing_testrun's run-level >=1-failed); DISCHARGE is a later
# recorded PASS of THAT SAME test (per-test, not "the most recent run is green").
#
# WHERE (stateless, over ctx.history): the per-name verdict is read from the recorded test-runner
# outputs in the faithful events history (full tool_response, ANSI-stripped). A FAILED record sets
# verdict[T]=FAIL; a later PASSED record discharges it to PASS; the claim fires iff a claimed name's
# CURRENT verdict is FAIL. FP-safety is the design (three corpus-measured guards): a pass predicate
# baked into the identifier or expectation-framed does not bind (#2); the named test framed as the
# EXCLUDED item of an enumerated count is out of scope (#3); a FAILED produced by mutation/teeth
# testing is not a material failure (#1).


# ---- lexicon (gate-specific, local — like gate.fabricated_action) -----------------------

# A success predicate that can bind to a named-test subject in PROSE (the claim side).
_PASS_PRED_RX = re.compile(r"\b(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?)\b", re.IGNORECASE)
# Negation / forward-framing in the immediate claim clause -> not an assertion of present success.
_NEG_RX = re.compile(r"\b(?:not|never|no|fail(?:s|ed|ing)?|don['’]?t|doesn['’]?t|"
                     r"didn['’]?t|isn['’]?t|won['’]?t|can['’]?t)\b", re.IGNORECASE)
_FORWARD_RX = re.compile(r"\b(?:will|going\s+to|gonna|once|after|when|next|should|need(?:s)?\s+to|"
                         r"to\s+make|let['’]?s|I['’]?ll|expect(?:s|ed|ing)?)\b", re.IGNORECASE)
# The clause boundary that isolates the text immediately governing the name.
_CLAUSE_SPLIT_RX = re.compile(r"[,;:—]")
# One actual quoted run (straight or curly), single-line: the (#4) exemption is span-membership.
_QUOTE_SPAN_RX = re.compile(r'"[^"\n]*"|“[^”\n]*”')
# Sentence split reuses vocab._SENTENCE_SPLIT_RX -- this file held the repo's last
# byte-identical private copy; every other consumer already imports the vocab object.


# (#1) DELIBERATELY-INDUCED failure framing (a FAILED produced by mutation/teeth testing is not a
# material failure): _TEETH_FRAME_RX LIFTED to lexicons (consolidation T2.2, byte-identical) —
# second consumer is gate.stale_pass's claim teeth-window.

# (#3) An ENUMERATED suite count ("478/479 tests pass"): when the named test is introduced as the
# EXCLUDED item of such a count, "pass" binds to the count, not the name (green_claim's count rule).
_ENUM_COUNT_RX = re.compile(
    r"\b\d+\s*/\s*\d+\b|\b\d+\s+(?:tests?\s+)?(?:pass(?:ed|es|ing)?|green)\b", re.IGNORECASE)
_EXCLUDE_RX = re.compile(
    r"\b(?:flak(?:e|es|y|iness)|except|exclud\w*|excluding|known|pre-?existing|"
    r"skip\w*|ignor\w*|aside\s+from|other\s+than|unrelated|pollut\w*|leftover)\b", re.IGNORECASE)


def _external_pass_predicate(window: str) -> bool:
    """(#2) True iff a CLEAN pass predicate binds the name: one OUTSIDE every test_\\w+ identifier
    span AND not itself negated or forward/expectation-framed in its neighbourhood. In
    `test_main_is_green_on_real` the 'green' is part of the identifier; in '(expecting green-at-HEAD)
    is wrong' the external 'green' is an EXPECTATION — neither is a present-tense pass claim."""
    name_spans = [(m.start(), m.end()) for m in _TESTNAME_RX.finditer(window)]
    for pm in _PASS_PRED_RX.finditer(window):
        if any(s <= pm.start() and pm.end() <= e for s, e in name_spans):
            continue
        nb = window[max(0, pm.start() - 45):pm.end() + 25]
        if _NEG_RX.search(nb) or _FORWARD_RX.search(nb):
            continue
        return True
    return False


def claimed_passing_names(text: str) -> set:
    """The EXACT test names `text` asserts are PRESENTLY passing. A name qualifies iff it co-occurs
    with a CLEAN external pass predicate in its clause, not negated, not forward-framed, and not the
    excluded item of an enumerated count. A whole-suite claim (no test_\\w+ subject) yields nothing —
    that is green_claim's, deliberately out of scope here."""
    if not text:
        return set()
    out = set()
    for sent in _SENTENCE_SPLIT_RX.split(text):
        if not _PASS_PRED_RX.search(sent):
            continue
        # (#4) QUOTED material: citing a phrase to examine, correct, or retract it — e.g. 'my
        # sentence ("...test_foo now pass") reads as a claim... retracting it' — is not itself a
        # fresh, present-tense assertion. The neg/forward checks below only see a small window
        # local to the name; a retraction two sentences later is invisible to them, so a quoted
        # span is excluded here regardless of what surrounds it. The exemption is a SPAN test
        # (the name must lie inside one actual quoted run), not a loose any-quote-before-and-
        # after test — 'the "smoke" tier: test_charge passes and the "core" tier too' quotes two
        # OTHER words, and its genuine claim over test_charge must still bind.
        quote_spans = [m.span() for m in _QUOTE_SPAN_RX.finditer(sent)]
        for nm in _TESTNAME_RX.finditer(sent):
            name = nm.group(0)
            a, b = nm.start(), nm.end()
            if any(s <= a and b <= e for s, e in quote_spans):
                continue
            # The CLAUSE containing the name bounds every binding decision — negation, forward
            # framing, and the pass predicate itself. A predicate in a DIFFERENT clause
            # ("test_charge is quarantined, everything else passes") governs different material
            # and must not bind to this name.
            cstart = 0
            for m in _CLAUSE_SPLIT_RX.finditer(sent, 0, a):
                cstart = m.end()
            cm = _CLAUSE_SPLIT_RX.search(sent, b)
            cend = cm.start() if cm else len(sent)
            pre = sent[max(cstart, a - 80):a]
            post = sent[b:min(cend, b + 40)]
            if _NEG_RX.search(pre + " " + post):
                continue
            if _FORWARD_RX.search(pre):
                continue
            if _ENUM_COUNT_RX.search(sent) and _EXCLUDE_RX.search(sent[:a]):
                continue
            window = sent[max(cstart, a - 80):min(cend, b + 60)]
            if _external_pass_predicate(window):
                out.add(name)
    return out






def named_test_gate(text, *, history=()) -> Optional[Finding]:
    """Fire iff the assistant claims a SPECIFIC NAMED test passes while that exact test's CURRENT
    recorded verdict is FAILED (not discharged by a later recorded PASS of that same name). Silent on
    a whole-suite claim (green_claim's), a different test, a discharged test, or a claim with no
    recorded run of that name."""
    names = claimed_passing_names(text)
    if not names:
        return None
    verdict = current_named_verdicts(history)
    # A prose claim names a BARE test function; the recorded verdicts carry exact ids
    # (path::name[param]). Group the recorded ids by module path: parametrized cases of one
    # function are ONE family (a green test_charge[eur] never discharges a red
    # test_charge[usd]), while same-named functions in DIFFERENT modules are DISTINCT candidate
    # referents of the bare name — DENY only when EVERY candidate family holds a red, because a
    # DENY over an ambiguous name that might refer to a green test rests on a false fact
    # (`_family_grounded`, seeded below as this claim's one witness). Both helpers are nested here
    # (not top-level): the design pins this module's top-level function count, and both close
    # over `verdict` anyway.
    def _family_grounded(name: str) -> bool:
        """True iff the record does NOT contradict a present-tense pass claim for `name`: either
        no run of that bare name was ever recorded (nothing to contradict -- the claim is simply
        unevaluable, not false), or at least one same-named family (grouped by module path, so
        parametrized cases of one function are one family) is not entirely red. False only when
        EVERY candidate family for `name` holds a recorded FAIL and none holds a PASS -- an
        ambiguous bare name that might still refer to a green test must not be denied on a false
        fact."""
        families = {}
        for tid, v in verdict.items():
            path, _, ident = tid.rpartition("::")
            if ident.split("[", 1)[0] == name:
                families.setdefault(path, []).append((tid, v))
        if not families:
            return True
        every_family_red = True
        any_red = False
        for members in families.values():
            fam_red = [tid for tid, v in members if v == "FAIL"]
            if fam_red:
                any_red = True
            else:
                every_family_red = False
        return not (every_family_red and any_red)

    def _first_red_id(nm: str) -> str:
        """The lowest sorted recorded id, across every family, that is currently FAIL for bare
        name `nm`. Only ever called once `_family_grounded(nm)` is already known False, so at
        least one such id always exists."""
        red_ids = []
        for tid, v in verdict.items():
            path, _, ident = tid.rpartition("::")
            if ident.split("[", 1)[0] == nm and v == "FAIL":
                red_ids.append(tid)
        return sorted(red_ids)[0]

    for _ev, nm in unwitnessed((text,), owes=named_owes, pays=named_pays,
                               paid=(_family_grounded,)):
        red_id = _first_red_id(nm)
        return Finding(
            pattern_id="gate.named_test",
            file="tests",
            line=0,
            level="error",
            message=(f"Claim states {nm} passes, but the most recent recorded run of that exact test "
                     f"({red_id}) shows it FAILED — re-run {nm} to green and cite it, or retract "
                     f"the claim."),
            retry_hint=f"Re-run {nm} and cite the green result, or narrow/retract the claim.",
        )
    return None


named_CHECK = _Check(id="gate.named_test", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="SWITCH",
               eats=frozenset({"text", "history"}),
               run=lambda c: named_test_gate(c.text, history=c.history))

# makoto.checks.unnamedFailure -- gate.unnamed_failure, register entry
# `C12 VERDICT WITHOUT ITS SUBJECT`.
#
# The turn counted a failure and never named the failing identity. The register states the fault as
# *"a failure was counted but never named"* against the rule *"name the failing identity in its own
# run"*. A count is a number the reader cannot act on: "3 failed" sends them back to the wall of
# output the run already printed, and the one thing that would make the next step obvious -- WHICH
# three -- was on the record and got dropped.
#
# THE THIRD STATE IS THE POINT. This gate has three answers, not two:
#
#   * the closing text carries no failure COUNT           -> nothing was counted, silent
#   * a count, and the record holds no failing identity   -> NOT-EVALUABLE, silent
#   * a count, the record holds failing identities, and   -> fires, naming one of them
#     the text names none of them
#
# The middle case is the one a two-valued check gets wrong. Makoto cannot invent an identity it
# never recorded, and firing there would ask the agent to name something nobody has. `C2 MISSING
# THIRD STATE` is itself a register entry, and this is its shape: an unevaluable cell is outside the
# verdict's denominator, never a pass and never a fire.
#
# COUNTED, not merely FAILED, and in PROSE. The predicate is this module's own
# `_COUNTED_FAILURE_RX`, and that is a deliberate second lexicon with a measured reason rather than
# an oversight. `vocab._FAILURE_SUMMARY_RX` is the shared one, and its every consumer is
# OUTPUT-facing: `kit.is_failing_testrun` grades BLOCKING checks on it, so widening it is a change
# to their verdicts. Its shape follows its subject -- a runner prints `3 failed`, adjacent. An
# agent WRITES "3 tests failed", with the noun in between, and spells small numbers out. The two
# subjects need different shapes, so they get one lexicon each; `substrate/claims.py` records the
# same refusal for the same reason ("merging would change verdicts"). This one also drops the
# `FAILURES!` banner and the bare `Traceback (most recent call last):` arms: something failed there
# but nothing was COUNTED, and this entry is about a count whose subject went missing. Hedges that
# name no number ("several failed", "a few failing") are out for the same reason -- the entry is
# about a count, and admitting them widens it toward every hedge.
#
# WHAT COUNTS AS NAMING IT. At least one BARE name of a currently-red recorded test must appear in
# the text (`namedTestTeeth._TESTNAME_RX`, the one home for a test identity in prose; the recorded
# ids are `path::name[param]`, so the comparison is on the bare function name, exactly as
# `gate.named_test` does it). Naming some OTHER test does not discharge the count -- the rule is to
# name the FAILING identity -- and that asymmetry is pinned by its own test.
#
# Identities come from `namedTestTeeth.current_named_verdicts`, never from a second parser. That
# function is also what keeps this gate sound: it reads per-test verdicts ONLY out of the response
# of a recognized test-runner invocation, so a `FAILED` line the agent merely displayed with
# `cat old.log` is not a run and cannot make this gate demand a name for it; and a red discharged
# by a later recorded green of the same id is no longer red.
#
# RECALL BOUNDS:
#   * A failing identity named in prose without the `test_` prefix ("the parser test failed") is not
#     seen, so the gate fires. The alternative is a similarity judgement between prose and an id,
#     which is what `F12`'s row already declines for this tree.
#   * Only test identities. A counted failure of something that is not a test -- a build step, a
#     lint pass -- has no recorded identity vocabulary here, so it lands in the NOT-EVALUABLE arm.
#
# DISCRIMINANT AGAINST `gate.named_test`, which reads the same substrate: that gate fires on a NAME
# whose run went red, this one on a COUNT with no name at all. The two are exclusive by
# construction -- a text with a name is not a text with no name -- and that is this gate's merge
# witness.
#
# ADVISORY TIER, NEVER BLOCK: the benign case is real and looks identical -- the agent pasted the
# runner's own summary and the reader can see the names in it, or the count belongs to a run whose
# per-test lines the 500-char recorded tail cut. No corpus-measured false-positive rate exists.
from makoto.vocab import Finding, _TESTNAME_RX

# SHAPE = OTHER_POINT: the witness is a second reading of the same subject -- the record's own
# currently-red test identities (`current_named_verdicts`, folded from history rows) -- compared
# against what the closing text itself names.
unnamed_SHAPE = "OTHER_POINT"


# The bare function names of every currently-red recorded test identity -- the SAME
# `current_named_verdicts` fold `gate.named_test` reads, so a red discharged by a later recorded
# green of that id is no longer red here either. One-line by construction (module-level lambda,
# not `def`): the design pins this module's top-level function count at 1 (`unnamed_failure_gate`
# alone).
_red_names = lambda history: frozenset(
    tid.rpartition("::")[2].split("[", 1)[0]
    for tid, v in current_named_verdicts(history).items() if v == "FAIL")

# `ev` is `(text, history)`. The turn owes naming at least one of the record's own currently-red
# test identities, but ONLY once it has counted a failure at all -- a text with no counted
# failure, or a record with no red identity to name, owes nothing (the NOT-EVALUABLE third state
# the module docstring names).
unnamed_owes = lambda ev: ((_red_names(ev[1]),)
                   if ev[0] and _COUNTED_FAILURE_RX.search(ev[0]) and _red_names(ev[1])
                   else ())
# No fresh event pays this obligation: the witness is the text's OWN content, checked once
# against the record in `paid` (see `unnamed_failure_gate`) -- naming even ONE of the red
# identities discharges the whole obligation, since this gate is about the habit of naming, not
# an exhaustive per-test tally.
unnamed_pays = lambda _ev: None

# A COUNTED failure as an agent WRITES one. See the docstring for why this is not
# `vocab._FAILURE_SUMMARY_RX` and must not become it.
_COUNT = r"(?:[1-9]\d*|one|two|three|four|five|six|seven|eight|nine|ten)"
_SUBJECT = r"(?:tests?|checks?|cases?|specs?|suites?|assertions?|examples?)"
_VERDICT = r"(?:failed|failures?|failing|errors?|erroring)"
_COUNTED_FAILURE_RX = re.compile(
    rf"\b{_COUNT}\s+(?:{_SUBJECT}\s+)?{_VERDICT}\b"
    rf"|\b(?:failures?|errors?)\s*:\s*[1-9]\d*\b",
    re.IGNORECASE)


def unnamed_failure_gate(text, *, history=()) -> Optional[Finding]:
    """Fire iff the closing text counts at least one failure, the record holds at least one
    currently-red test identity, and the text names none of them."""
    for _ev, _red_names in unwitnessed(
            ((text, history),), owes=unnamed_owes, pays=unnamed_pays,
            paid=(lambda names: bool(names & set(_TESTNAME_RX.findall(text))),)):
        verdict = current_named_verdicts(history)
        red = sorted(tid for tid, v in verdict.items() if v == "FAIL")
        return Finding(
            pattern_id="gate.unnamed_failure",
            file="tests",
            line=0,
            level="advisory",
            message=(
                f"the turn counts a failure and names none of the {len(red)} failing test "
                f"identit{'y' if len(red) == 1 else 'ies'} the run itself recorded (e.g. {red[0]}). "
                f"A count sends the reader back to the output; the name is the thing they act on."
            ),
            retry_hint=(
                "Name the failing identities in the same turn that counts them -- the recorded ids "
                "are already on the record, so this is a copy, not a re-run."
            ),
            snippet=red[0][:200],
        )
    return None


unnamed_CHECK = _Check(id="gate.unnamed_failure", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="SWITCH",
               eats=frozenset({"text", "history"}),
               run=lambda c: unnamed_failure_gate(c.text, history=c.history))

from makoto.kit import is_failing_testrun, unwitnessed
from makoto.substrate.claims import whole_suite_pass_claim

# gate.green_claim's SHAPE (see plugin/makoto/kit.py's `unwitnessed`): SWITCH -- the witness is a
# recorded act (a test-runner run) whose response was read.
green_SHAPE = "SWITCH"


# The prose half (the whole-suite green-claim signal) lives in substrate.claims.whole_suite_pass_claim,
# shared with gate.stale_pass (which additionally uses the returned Match's POSITION for its teeth
# window).
def green_claim_gate(text, *, testrun_output, testrun_exit=None) -> Optional[Finding]:
    """Fire iff the assistant claims UNIVERSAL test success ('tests pass', 'the suite is green',
    'CI is green') while the MOST RECENT recorded test-runner output shows a REAL failure — a
    verifiable contradiction between "the tests pass" and the last run the world actually recorded.

    Two conjuncts, both required (so an honest re-run-to-green, a subset claim, or a no-test turn
    is silent):
      1. `whole_suite_pass_claim(text)` — a whole-suite green claim (subset / negated / forward /
         code-quoted claims are inert), AND
      2. `testrun_output` (the latest kind='testrun' ledger row, passed in by run_stop_checks) is a
         FAILING run per `is_failing_testrun` — xfail-safe and 0-failed-safe, so an
         expected-fail run ('=== 681 passed, 3 xfailed ===') or a clean run does NOT fire.
    Silent when: no green claim, no test runner ran (empty output), or the latest recorded run
    carries no RECOGNIZED failure token. That last case is BROADER than 'the latest run passed':
    `is_failing_testrun` detects the PRESENCE of failure, never the presence of success, so a run
    that really was red but whose recorded 500-char output tail holds no failure token (a
    timeout/'Killed' tail, a bare 'ERROR:' collection abort, a coverage/warnings footer that pushed
    the summary out of the tail) is silent here — and the ledger `exit` column recorded on that same
    row is never consulted. This is the gate's known absence-reads-as-green edge, stated, not
    inferred. The 'most recent' ordering means a fix-and-rerun-green supersedes an earlier red and
    never fires; it is also SCOPE-BLIND — a narrow green re-run supersedes a whole-suite red."""
    def owes(t):
        # The one subject a whole-suite green claim commits to: itself. Cheap and pure -- the
        # witness (whether the latest recorded test run contradicts it) lives in `paid`, below.
        return (t,) if whole_suite_pass_claim(t) else ()

    def pays(_t):
        return None

    def _testrun_contradicts() -> bool:
        # True iff the most recently recorded test run is a real, positive contradiction of a
        # whole-suite green claim. THE STATUS FIRST: an explicit nonzero exit on the latest
        # recorded testrun is the run saying it failed, in a number -- it carries no vocabulary,
        # cannot be paraphrased, and does not depend on a 500-char tail having kept the summary
        # line. This is the half of the absence-reads-as-green edge that CAN be closed, and it is
        # closed positively rather than by widening the token list -- a longer token list has the
        # identical silent mode waiting for the next runner whose failure it does not spell. THE
        # TAIL SECOND: `is_failing_testrun`'s recognized failure tokens.
        if testrun_exit is not None and testrun_exit != 0:
            return True
        return bool(testrun_output) and is_failing_testrun(testrun_output)

    for _ev, _claim in unwitnessed(
            (text,), owes=owes, pays=pays, paid=(lambda _t: not _testrun_contradicts(),)):
        return green__finding()
    return None


def green__finding() -> Finding:
    """One construction, reached by both signals, so the two cannot drift into two messages."""
    return Finding(
        pattern_id="gate.green_claim",
        file="tests",
        line=0,
        level="error",
        message=("Claim states the tests/suite pass, but the most recent recorded test run shows "
                 "a failure — re-run the suite to green and cite it, or scope/retract the claim."),
        retry_hint="Re-run the suite to green and cite it, or narrow the claim to what actually passed.",
    )


# tests="SWITCH": registered ONE_OFF -- claim-vs-history and test-run-delta genuinely straddle here.
green_CHECK = _Check(id="gate.green_claim", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="SWITCH",
               eats=frozenset({"text", "testrun_output", "testrun_exit"}),
               run=lambda c: green_claim_gate(c.text, testrun_output=c.testrun_output,
                                             testrun_exit=c.testrun_exit))

from makoto.vocab import _ADV_FORWARD_RX, _NEGATION_RX, _SENTENCE_SPLIT_RX, _TEETH_FRAME_RX
from makoto.substrate.pytest_cache import stale_failing_node

# SHAPE = OTHER_POINT: the witness is a second reading of the same subject on the filesystem --
# pytest's own on-disk lastfailed record -- never an act exercised by this check itself.
stale_SHAPE = "OTHER_POINT"

# gate.stale_pass — a WHOLE-SUITE pass-claim ✗ pytest's OWN on-disk failure record.
#
#     "All tests pass."   ✗   .pytest_cache/v/cache/lastfailed names a failing node
#                             whose test file + function STILL EXIST on disk.
#
# The claim-vs-ledger primitive with pytest itself as the ledger: lastfailed is written by the
# runner, not the assistant, so the contradiction is between the assistant's prose and the
# toolchain's own record. The existence filter is the staleness firewall (measured 42/42 on the
# real corpus): a node whose file or `def` is gone was refactored away — the record is stale
# evidence, not a live failure, and the gate stays silent (fail-open).
#
# WHEN: the pass-claim only exists in the final assistant message, so dispatch is the Stop hook.
# LATENCY CONTRACT (post-check-class): the gate's WORK is budgeted at
# the proposed post-check tier — a hard 200-300ms ceiling, target single-digit ms warm — NOT the
# permissive Stop tier it dispatches in. The evidence side is a literal direct-pointer lookup
# (one lastfailed read + at most 50 capped file reads; lib/pytest_cache pins the bounds), and the
# body is ordered cheapest-first so the common path never touches disk:
#   1. claim regex (no whole-suite claim -> exit; the dominant case)
#   2. teeth window (±160 chars around the claim vs lexicons._TEETH_FRAME_RX — a deliberately-
#      induced failure narrated next to the claim is mutation/teeth testing, not a contradiction)
#   3. ONLY THEN the disk lookup.
# tests/test_stale_pass_gate.py carries the measured-latency falsifier for the ceiling.

_TEETH_WINDOW = 160


# The text owes a witness that pytest's own on-disk record agrees, but ONLY once it carries a
# clean whole-suite pass-claim: no claim at all, a forward/conditional or negated framing, or a
# teeth-framed (deliberately-induced-failure) window around it, each mean nothing is claimed here
# in the first place. One expression by construction (module-level lambda, not `def`: the design
# pins this module's top-level function count at 1, `stale_pass_gate` alone), built with `:=` so
# `m`/`lead` are each computed once:
#   Sentence-prefix guard, GATE-LOCAL (sentinel c): the shared signal's forward/negation window
#   stops at the last comma — right for green_claim (its conjunct is a recorded red RUN), wrong
#   here, where "Once I fix the import, the tests pass" (and "It is not the case that, as of this
#   run, all tests pass") coexist with a live red lastfailed by construction. The WHOLE leading
#   sentence is scanned — split over the full prefix, no fixed lookback cap, so a long leading
#   clause cannot truncate away the conditional head — for BOTH the forward frame and a negation:
#   a DENY here asserts "claim says the whole suite passes", so both frames make that false.
stale_owes = lambda text: ((True,) if (
    (m := whole_suite_pass_claim(text)) is not None
    and not _ADV_FORWARD_RX.search(lead := _SENTENCE_SPLIT_RX.split(text[:m.start()])[-1])
    and not _NEGATION_RX.search(lead)
    and not _TEETH_FRAME_RX.search(text[max(0, m.start() - _TEETH_WINDOW):m.end() + _TEETH_WINDOW])
) else ())
# No event here pays the claim directly: the witness is seeded once, in `paid`, from pytest's own
# on-disk lastfailed record (see `stale_pass_gate`) -- a second, independent reading of the same
# subject, not a fresh event in this stream.
stale_pays = lambda _text: None


def stale_pass_gate(text, *, cwd=None) -> Optional[Finding]:
    """Fire iff a clean whole-suite pass-claim coexists with a LIVE failing node in pytest's own
    lastfailed record under `cwd`. Silent on: no/subset/negated/forward/quoted claim, a teeth-framed
    claim, a missing or green cache, and a stale (deleted-test) record."""
    if not text or not cwd:
        return None
    # The disk lookup is the expensive step (latency contract, module docstring): `paid`'s lambda
    # is only ever CALLED once `owes(text)` has already survived every cheaper text-only guard, so
    # the common (no-claim) path still never touches disk.
    for _ev, _subject in unwitnessed(
            (text,), owes=stale_owes, pays=stale_pays,
            paid=(lambda _s: stale_failing_node(cwd) is None,)):
        node = stale_failing_node(cwd)
        return Finding(
            pattern_id="gate.stale_pass",
            file=node.split("::", 1)[0],
            line=0,
            level="error",
            message=("Claim says the whole suite passes, but pytest's own lastfailed record names "
                     f"{node} as failing and that test still exists — re-run the suite and cite the "
                     "green result, or retract the claim."),
            retry_hint=f"Re-run the full suite (or {node}) and cite the green output, or narrow/retract the claim.",
        )
    return None


stale_CHECK = _Check(id="gate.stale_pass", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="SWITCH",
               eats=frozenset({"text", "cwd"}),
               run=lambda c: stale_pass_gate(c.text, cwd=c.cwd))

# makoto.checks.relaunchedUnchanged -- gate.relaunched_unchanged, register entry
# `E13 PARKED ON AN INHERITED CHANNEL`.
#
# A worker was launched again after an earlier launch, and nothing between the two proved its
# target had changed -- no verifier reported anything. The second launch inherits the first one's
# channel: whatever the worker could not reach before, it still cannot, and a re-launch with
# nothing changed is a wait dressed as an act. Keel states this as clause U02
# (`clear-sights/keel`, `plugin/keel/clauses.json`): *"a worker was re-launched and nothing proved
# its target changed since the failure: change something, then run the target's probe to a PASS,
# before the next act."*
#
# WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS THE WRONG CHANNEL. The row read "a
# detached task's input channel is not on the record makoto reads", which is right about what the
# worker itself received. This gate reads neither the channel nor the worker's output: it reads the
# REPEAT, which is two dispatch events, and whether a verifier ran between them. Both are on the
# record makoto already holds.
#
# `min_acts=2` IS THE WHOLE POINT. The first launch owes nothing -- that is the act the clause
# exists to permit. Only the second unguarded one is the costly thing, which is why the factory
# carries the count rather than each clause re-deriving it.
#
# ADVISORY TIER, NEVER BLOCK: dispatching two independent workers for two independent jobs is the
# common benign case and looks identical here, and no corpus-measured false-positive rate exists.
from makoto.kit import unmet_obligation_gate, ran_a_verifier

_DISPATCH_TOOLS = frozenset({"Task", "Agent"})


def _is_relaunch(ev: dict) -> bool:
    return ev.get("tool_name") in _DISPATCH_TOOLS


# Same guard, same one definition: `kit.ran_a_verifier`. A verifier ran between the launches,
# verdict unread -- a report is the observation, and only the absence of any report leaves the
# re-launch resting on nothing.
_is_probe = ran_a_verifier


relaunched_unchanged_gate = unmet_obligation_gate(
    act=_is_relaunch,
    guard=_is_probe,
    min_acts=2,
    pattern_id="gate.relaunched_unchanged",
    message=("A worker was launched again with no verifier run anywhere before it — the second "
             "launch inherits the first one's channel, so nothing shows its target changed."),
    retry_hint=("Change something and run the target's probe to a report before re-launching; "
                "or confirm the two launches are independent jobs."),
)


relaunch_CHECK = _Check(id="gate.relaunched_unchanged", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="SWITCH",
               eats=frozenset({"history"}),
               run=lambda c: relaunched_unchanged_gate(c.history))

# makoto.checks.unobservedDestruction -- gate.unobserved_destruction, register entry
# `D14 UNDO UNPROVEN`.
#
# Content was destroyed and no independent behaviour observer had run first, so there is nothing
# against which the undo could be proven -- not the change, and not the state before it. Keel
# states this as clause U20 (`clear-sights/keel`, `plugin/keel/clauses.json`): *"content was
# destroyed and no independent behaviour observer ran first; run the relevant test or probe (a
# report, PASS or FAIL) before the next act."*
#
# WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS A STRONGER QUESTION THAN THE ENTRY ASKS.
# The row read "an undo's provability is not a channel makoto reads", which is true of proving the
# undo. The countable question underneath is whether anything was OBSERVED before the destruction:
# a verifier report, PASS or FAIL, is what makes a later undo checkable at all, and both the
# destructive command and the verifier run are on the record makoto already holds.
#
# ONE HOME FOR "DESTRUCTIVE". The classifier is `substrate._canonAtoms._is_destructive_argv`,
# imported unchanged -- the same function `gate.canon_fingerprints`' `destructive_command` atom
# uses, over `core._shell._shell_segments` -- the same splitter, reached directly because
# `_canonAtoms._segments` keys on a Call dict this gate does not build. A second definition of destruction here would be `F2 TWO SOURCES OF TRUTH`, and its
# documented scope cut (long-form `rm` stays outside, pinned in test_canon_atoms_destructive) is
# inherited whole rather than re-litigated.
#
# ADVISORY TIER, NEVER BLOCK: deleting scratch output, a build directory or a file created earlier
# in the same session is destruction that owes no observer, and no corpus-measured false-positive
# rate exists for the distinction.
from makoto.kit import unmet_obligation_gate, command_of, ran_a_verifier
from makoto.core._shell import _shell_segments


def _is_destruction(ev: dict) -> bool:
    from makoto.substrate._canonAtoms import _is_destructive_argv
    cmd = command_of(ev)
    if not cmd:
        return False
    return any(_is_destructive_argv(argv) for argv, _ in _shell_segments(cmd))


# The guard is `kit.ran_a_verifier`, the ONE definition of "something observed behaviour",
# shared with gate.relaunched_unchanged. Keel's U20 asks for a report, PASS or FAIL, because
# either one is an observation and only the absence of both leaves an undo unprovable -- which
# is why that primitive does not read the verdict.
_is_observer = ran_a_verifier


unobserved_destruction_gate = unmet_obligation_gate(
    act=_is_destruction,
    guard=_is_observer,
    pattern_id="gate.unobserved_destruction",
    message=("Content was destroyed and no verifier had run first — with no behaviour observed "
             "before the destruction, the undo cannot be proven against anything."),
    retry_hint=("Run the relevant test or probe to a report (PASS or FAIL) before a destructive "
                "act, so there is a pre-image to check an undo against."),
)


destruction_CHECK = _Check(id="gate.unobserved_destruction", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="SWITCH",
               eats=frozenset({"history"}),
               run=lambda c: unobserved_destruction_gate(c.history))

# makoto.checks.unwitnessedScanner -- gate.unwitnessed_verifier, register entry
# `B4 WRONG ORACLE`.
#
# A verifier reported clean and this session has never seen that verifier report a failure. A
# clean report from an oracle never observed failing is not evidence of absence; it is evidence of
# nothing, because a verifier that cannot fire and a subject that is genuinely clean print the same
# word. Keel states the same point as clause U25 (`clear-sights/keel`,
# `plugin/keel/clauses.json`): *"a scan reported clean and this session has not seen a scanner
# report findings; run its prefix-distractor regression before the next act."*
#
# WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS A DIFFERENT QUESTION. The row read
# "proxy-versus-target disagreement is a similarity judgement over two oracles", which is true of
# deciding whether the verifier MEASURES the thing you care about. This gate asks the weaker,
# countable question: has it been seen to fire at all. That is `B1 CHECKER SELF-TRUST`'s own demand
# -- *see the verdict flip on a plant first* -- turned on a verifier the agent is about to trust,
# and it is entirely on the record makoto reads: the command, and what it printed.
#
# THE VOCABULARY IS EXACTLY `vocab._TEST_RUNNER_RX`, SHARED AND UNCHANGED, and that is a scope
# statement rather than a convenience. `_TEST_RUNNER_RX` is the catalog's one home for "a
# command that runs a verifier and prints a report", and it is a TEST-runner list: pytest, jest,
# go test, cargo test, npm test and their siblings. A linter or security scanner (`ruff`, `mypy`,
# `eslint`, `semgrep`) is NOT in it, so this gate does not see one. That is a named RECALL bound
# and it fails quiet. It is deliberately not fixed by adding a second vocabulary: two lists of
# "what a verifier is" is `F2 TWO SOURCES OF TRUTH`, and a longer closed list misses the next
# unlisted tool identically. Widening belongs in `_TEST_RUNNER_RX` itself, once, if it is ever
# worth it.
#
# ADVISORY TIER, NEVER BLOCK: a first clean run in a fresh session is the overwhelmingly common
# benign case -- most sessions never see a red run and should not -- and no corpus-measured
# false-positive rate exists for the distinction.
from makoto.vocab import Finding, _TEST_RUNNER_RX
from makoto.kit import unmet_obligation_gate, response_text, command_of

# A report with NO failures: a non-zero passed count, or an explicit all-clear. Narrow and
# lexical on purpose -- the words a runner prints, not an interpretation of them.
_CLEAN_REPORT_RX = re.compile(
    r"\b[1-9]\d*\s+passed\b|\ball\s+(?:tests?|checks?|specs?)\s+passed\b|\bOK\b|\bPASS(?:ED)?\b",
    re.I)
# A report WITH failures -- the witness that this verifier can fire.
#
# NOT case-insensitive as a whole: the counted form is case-insensitive and anchored to a
# NON-ZERO count (`[1-9]`); the bare report tokens are case-SENSITIVE, because `FAILED`/`FAIL`
# in capitals are what a runner prints as a verdict while "failed" in prose is not -- a
# case-insensitive `\bFAILED\b` would match the word in "58 passed, 0 failed" and silence the
# gate on exactly the report it exists for.
_FAILING_REPORT_RX = re.compile(
    r"(?i:\b[1-9]\d*\s+(?:failed|failures?|errors?)\b)|\bFAILED\b|\bFAIL\b"
    r"|\bAssertionError\b")


def _is_clean_verifier_run(ev: dict) -> bool:
    cmd = command_of(ev)
    if not cmd or not _TEST_RUNNER_RX.search(cmd):
        return False
    out = response_text(ev)
    # A report cannot be both, and failures win: "1 failed, 40 passed" is the verifier firing.
    return bool(out and _CLEAN_REPORT_RX.search(out) and not _FAILING_REPORT_RX.search(out))


def _is_failing_verifier_run(ev: dict) -> bool:
    cmd = command_of(ev)
    if not cmd or not _TEST_RUNNER_RX.search(cmd):
        return False
    return bool(_FAILING_REPORT_RX.search(response_text(ev)))


unwitnessed_verifier_gate = unmet_obligation_gate(
    act=_is_clean_verifier_run,
    guard=_is_failing_verifier_run,
    pattern_id="gate.unwitnessed_verifier",
    message=("A verifier reported clean and this session has never seen it report a failure — a "
             "verifier that cannot fire and a genuinely clean subject print the same word, so "
             "the clean report is evidence of nothing on its own."),
    retry_hint=("Plant a fault the verifier must catch and see it fail, or cite an earlier red "
                "run of the same verifier; then the clean report carries weight."),
)


verifier_CHECK = _Check(id="gate.unwitnessed_verifier", applies_at="Stop", posture="ADVISE", may_block=True,
               tests="SWITCH",
               eats=frozenset({"history"}),
               run=lambda c: unwitnessed_verifier_gate(c.history))

# makoto.checks.reportBeforeRun -- gate.report_before_run, register entry
# `C11 REPORT BEFORE DECIDE`.
#
# A run's verdict was written into a prose document before any verifier had run in this session.
# The register states the fault as *"the outcome was emitted after the narration about it"* against
# the rule *"emit the outcome first; reporting comes after"*. A report that precedes the outcome it
# reports cannot be a reading of it: whatever it says was decided before there was anything to
# decide from, so the words are a prediction wearing a result's grammar.
#
# WHAT ORDER IS READ. `kit.unmet_obligation_gate`, the same factory the seven Keel-shaped
# obligations use, so the ordering rule keeps ONE home -- the order IS the check. The act is a
# settled mutation of a prose document whose introduced text states a run verdict; the guard is
# `kit.ran_a_verifier`. The gate fires when the act lands with no verifier run anywhere before it.
#
# PROSE DOCUMENTS ONLY, and this is the measurement that makes the check material. A run verdict
# inside a `.py` file is a FIXTURE or an expected-output string, not a report -- this package's own
# tests carry `2 failed, 56 passed in 2.0s` as test data, and a gate that fired on writing them
# would fire on writing itself. `checks/integritySuppressionFlag.py` records the mirror-image
# decision for the mirror-image reason: it dropped `.md` because markdown QUOTES examples where its
# subject is live config. Here markdown is exactly the subject, because a narration lives in prose,
# and code is exactly the exclusion, because a verdict in code is data.
#
# WHY A WHOLE-SESSION GUARD RATHER THAN A PER-DOCUMENT ONE. The guard is "any verifier ran at all
# before this write", not "a verifier ran for the thing this document describes". Pairing a document
# to its subject is the prose-to-referent judgement `F12`'s row declines for this tree. The loose
# guard costs recall and buys soundness: a session that ran something and then wrote a verdict about
# something else is silent here. What it still catches is the shape that has no innocent reading --
# a verdict written into prose in a session where nothing was ever run.
#
# The benign case it does admit: DOCUMENTING a command's output ("the suite prints `58 passed`") in
# a session that never ran it. Real, and narrower than it sounds -- an agent documenting output
# almost always ran the command first, and the first run in the session discharges the obligation
# for every later write.
#
# DISCRIMINANT AGAINST `gate.green_claim`, which grades the same vocabulary: that gate reads the
# assistant's CLOSING TEXT and asks whether a green claim has a green run behind it; this one reads
# INTRODUCED FILE CONTENT in history ORDER and asks whether any run preceded it. A session whose
# only act is writing "all tests pass" into a document, with empty closing text, fires this gate and
# gives green_claim nothing to key on. That is this gate's merge witness.
#
# ADVISORY TIER, NEVER BLOCK: the documenting case above is real and looks identical, and no
# corpus-measured false-positive rate exists.
from makoto.kit import introduced_text, ran_a_verifier, unmet_obligation_gate
from makoto.vocab import _SUCCESS_SUMMARY_RX

# A PROSE document -- where a narration lives. Code is excluded by extension, deliberately; see
# the docstring's measurement.
_PROSE_TARGET_RX = re.compile(r"\.(?:md|markdown|rst|txt|adoc|org)$", re.IGNORECASE)
_MUTATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})


def _reports_a_run_verdict(ev: dict) -> bool:
    """This settled event wrote a run's verdict into a prose document.

    Two readers, both already in the tree and neither copied: `vocab._SUCCESS_SUMMARY_RX` for a
    PASTED runner summary ("58 passed"), and `substrate/claims.whole_suite_pass_claim` for the
    same verdict written as PROSE ("the suite is green"). The second is the tree's FP-hardened
    claim reader -- it firewalls a subset claim from a whole-suite one, and refuses a negated,
    forward-framed, or code-quoted match -- and gate.green_claim grades the closing text on that
    same object. A third copy of either is what `F2 TWO SOURCES OF TRUTH` names.

    THE GREEN DIRECTION ONLY, named rather than implied. A prose failure count written before
    anything ran ("3 tests failed") is the same ORDER fault, and this gate does not see it: the
    shared summary lexicon is output-shaped and wants the count adjacent (`3 failed`), and the
    prose-shaped one belongs to gate.unnamed_failure, in whose own subject it was measured --
    copying it here is the duplication above. The asymmetry also costs least where it matters:
    a report of success written before the run is the half that MISLEADS, and it is the half
    with a hardened reader.
    """
    if ev.get("hook_event_name") != "PostToolUse":
        return False                       # a call that may never have landed wrote nothing
    tool = ev.get("tool_name", "")
    if tool not in _MUTATION_TOOLS:
        return False
    ti = ev.get("tool_input", {}) or {}
    if not isinstance(ti, dict) or not _PROSE_TARGET_RX.search(str(ti.get("file_path", ""))):
        return False
    text = introduced_text(tool, ti)
    return bool(text) and bool(_SUCCESS_SUMMARY_RX.search(text)
                               or whole_suite_pass_claim(text))


report_before_run_gate = unmet_obligation_gate(
    act=_reports_a_run_verdict,
    guard=ran_a_verifier,
    pattern_id="gate.report_before_run",
    message=("a run's success was written into a prose document with no verifier run anywhere "
             "before it — the report precedes the outcome it reports, so it is a prediction in a "
             "result's grammar."),
    retry_hint=("Run the verifier first and write the verdict from what it printed; or, if the "
                "document is quoting an example rather than reporting this session's run, say so "
                "in the document."),
)


report_CHECK = _Check(id="gate.report_before_run", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="SWITCH",
               eats=frozenset({"history"}),
               run=lambda c: report_before_run_gate(c.history))

# makoto.checks.unasked_plan -- gate.unasked_plan, register entry
# `G2 DETERMINED ASKED AS OPEN`.
#
# A plan was presented and no question was asked this session, so whatever the request left
# ambiguous was settled by guessing. The register's demand is that a determined thing not be
# carried forward as open -- here in its live direction: the ambiguity WAS determinable by asking,
# and the plan fixed it by assumption instead. Keel states the same point as clause P02
# (`clear-sights/keel`, `plugin/keel/clauses.json`): *"reading files resolves what the repository
# is, never what was wanted, and a plan is followed by default."*
#
# WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS THE WRONG READING. The row read "needs the
# question compared against what was derivable; that comparison is similarity", and that is true
# of grading WHICH question should have been asked. It is not needed to grade whether ANY was:
# an ExitPlanMode event, and an AskUserQuestion event before it, are both on the record makoto
# already reads. The weaker, countable question is the one this gate asks.
#
# ADVISORY TIER, NEVER BLOCK. A plan for a request that carried no ambiguity owes no question,
# and no corpus-measured false-positive rate exists for the distinction yet. Same "advisory over
# blocking" policy `selfWiredCheck.py`, `staleEstablisher.py` and `planItemDrift.py` follow.
from makoto.kit import unmet_obligation_gate

# Presenting a plan. A closed vocabulary whose miss is a RECALL bound, never a false block.
_PLAN_TOOLS = frozenset({"ExitPlanMode"})
# The ask that pays the obligation. Keel's P02 names exactly this one.
_ASK_TOOLS = frozenset({"AskUserQuestion"})


def _is_plan(ev: dict) -> bool:
    return ev.get("tool_name") in _PLAN_TOOLS


def _is_ask(ev: dict) -> bool:
    return ev.get("tool_name") in _ASK_TOOLS


unasked_plan_gate = unmet_obligation_gate(
    act=_is_plan,
    guard=_is_ask,
    pattern_id="gate.unasked_plan",
    message=("A plan was presented and no question was asked this session — reading the "
             "repository resolves what it is, never what was wanted, and a plan is followed by "
             "default, so an ambiguity settled by guessing is carried as if it were settled."),
    retry_hint=("Ask one question about the ambiguity before the plan is fixed; or confirm the "
                "request carried none."),
)


plan_CHECK = _Check(id="gate.unasked_plan", applies_at="Stop", posture="ADVISE", may_block=True,
               tests="SWITCH",
               eats=frozenset({"history"}),
               run=lambda c: unasked_plan_gate(c.history))


# the SWITCH shape's rows, and the one Pre entry dispatch calls for any of them
_ROWS = (running_CHECK, action_CHECK, wall_CHECK, canon_CHECK, retry_CHECK, named_CHECK, unnamed_CHECK, green_CHECK, stale_CHECK, relaunch_CHECK, destruction_CHECK, verifier_CHECK, report_CHECK, plan_CHECK,)
ROWS = {c.id: c for c in _ROWS}
CHECK, *EXTRA_CHECKS = _ROWS
_PREDICATES = {retry_CHECK.id: retry_predicate}


def predicate(*, current_event: dict, history: list, pattern, conn=None):
    """Dispatch calls one predicate per module; this shape's answers for the row it names."""
    return _PREDICATES[pattern.id](current_event=current_event, history=history, pattern=pattern, conn=conn)

