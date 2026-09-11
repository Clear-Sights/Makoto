"""canon's Stop-gate engine + adapter (SPEC-5 Task 4, owner-revised layout: formerly
`stopchecks/canon.py` + `stopchecks/stopcheck_canon.py`, combined into one flat file here — same
single-file choice as `hollowTest.py`/`deadPureStatement.py`; see `hollowTest.py`'s module
docstring for the rationale).

Ported from the read-only ancestor `makoto-dev` (canon/agnostic_gate.py) to live makoto's own
file layout. The engine half (primitives + the history->Call adapter) is PURE: stdlib only
(json/dataclasses/typing/__future__) — no makoto import at all — so the gate-shape import
firewall (tests/test_import_direction.py, the pipeline-order firewall) is satisfied by construction for that
half; the adapter half below (`canon_gate`/`GATE`/`CHECK`) is what actually imports
`makoto.vocab`/`makoto.context`.

A primitive here reads the closed agnostic terminal set: {tool_name, tool_input identity,
interrupted, self_error_code}. No language- or test-runner-specific regex appears. `canon.recur`
also uses `kit.classify_failure` over the host-emitted error text only to budget confidently
transient failures; its markers are generic failure vocabulary, never runner or language tokens.
Two primitives are installed:

  * canon.timeout — `timed_out_at_turn_end`: the turn closed with the LAST decoded call in a
    direct error state (interrupted or a self-emitted error code) — NOT "any call errored
    somewhere", because a resolved-then-fixed error must stay silent. One confidently transient,
    non-interrupted failure is also silent; an explicit harness interruption and deterministic or
    uncertain errors retain the one-call bar.
  * canon.recur   — `recur_stuck`: the SAME tool call (identical tool_name + byte-identical
    tool_input) re-issued in a CONSECUTIVE run of length >=2 where EVERY call in that run is in
    a direct error state — a stuck retry loop with nothing changed between attempts. A run of
    confidently transient failures gets one extra re-poll: it becomes stuck only after that key
    has accumulated three transient failures across the stream, reset by that key's success;
    deterministic and uncertain failures keep the two-call bar. Verdict is judged per KEY at the
    END of each maximal consecutive run, and the LAST judgment for each key wins — so a later
    success for the same key silences it even when other, different calls happened in between.
    See docs/adr/0022-recur-stuck-latest-run-wins.md for the decision history.

PATTERN_ID CONVENTION (deliberate divergence from the read-only ancestor `makoto-dev`, found
while porting): the ancestor's canon_gate emitted pattern_id=f"canon.{cid}" (e.g. "canon.timeout",
"canon.recur") per fired sub-primitive. Live makoto's `dispatch._blocking_gate_ids()` derives the
blocking set from `{c.id for c in load_checks(edge="Stop") if c.may_block and c.posture == BLOCK}`
— i.e. the CHECK's OWN id ("gate.canon") — and filters gate_findings by `finding.pattern_id in
_blocking_gate_ids()`. EVERY other live gate (gate.dropped, gate.liveness, gate.hollow_test,
gate.self_wired, ...) always stamps `pattern_id == its own CHECK id`, one shape per gate, even when
a gate can yield several findings (gate.liveness/gate.hollow_test can fire more than once per turn,
always under their own single pattern_id). Keeping the ancestor's per-primitive pattern_id here
would make `canon.timeout` / `canon.recur` findings silently INVISIBLE to `_blocking_gate_ids()` —
discovered, audited, but never actually blocking, defeating the whole point of this being a
blocking gate. So this port stamps `pattern_id="gate.canon"` (matching the CHECK id, like every
sibling gate) and keeps the
sub-primitive identity in the MESSAGE instead, prefixed `"canon.<id>: "` — callers/tests that need
to know which sub-primitive fired read the message, exactly as the ticket anticipated ("a
`gate.canon` finding whose message reflects the timeout primitive").

LEVEL: "error" — the ONLY blocking level in live makoto (makoto.vocab._ALLOWED_FIRE_LEVELS ==
{"error"}; dispatch._emit_decision maps level=="error" to posture.BLOCK, the only outcome that
renders as a block). This is an ORDINARY blocking gate, NOT the one advisory exception
`gate.self_wired` uses.

IMPORT FIREWALL (tests/test_gate_shape.py::test_no_gate_module_imports_a_sibling_or_cross_l2):
imports ONLY makoto.vocab, makoto.context, and the pure primitives below (intra-module,
no cross-module import needed post-merge — see the layout note above).
"""
from __future__ import annotations
import json
import os
import re
from typing import Iterable, List

from makoto.vocab import Finding
from makoto.kit import canon_input, classify_failure, decode_history_event, failure_terminal_result

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
    Bash tool_response in this repo. See docs/adr/0023-canon-exit-code-terminal-key.md for the
    decision history."""
    return _result(c).get("exitCode")


def self_error_code(c: Call):
    """agnostic terminal `self_error_code`: a harness-emitted error code/object on the result.
    PRESENCE-based for the `error` field: a present, non-None `error` — even a falsy one such
    as `""` — is a self-reported error state (the old `or`-chain collapsed `{"error": "",
    "error_code": 0}` to None, so a turn closing on that terminal read green). `error_code`
    keeps the truthy requirement: `0` is the conventional success code, not an error."""
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
    sandbox-bypass escape hatch. Reads `input.dangerouslyDisableSandbox` — confirmed as a real
    tool_input schema key by this repo's own signal-miner corpus decoder (`REF-lever-graded-
    primitives/signalminer/peeler/agnostic.py` SCHEMA_KEYS, grouped with known Bash/Read
    tool_input fields it has actually observed in real sessions), not a guessed name. Absence
    (the overwhelmingly common case) returns False, never crashes. Observability-only: no
    primitive reads it yet."""
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
    bad verdict for that same key and resets its transient budget. See
    docs/adr/0022-recur-stuck-latest-run-wins.md for the decision history."""
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
        # Dunder-insensitive verdict identity (`_pairing_input`, like the Pre<->Post pairing):
        # a harness bookkeeping key that VARIES per call (`__seq`) split a byte-identical retry
        # loop into distinct keys, so recur never saw a run of length >= 2 — the injection
        # class ADR 0024 documents, previously guarded on the pairing side only. A leading
        # `__` is transport bookkeeping, never call semantics, so folding it cannot collapse
        # two genuinely distinct calls (the same argument ADR 0024 makes for pairing).
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
    return any(last_bad.values())


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
    if interrupted(last):
        return True
    error = self_error_code(last)
    if error is None:
        return False
    text = str(error)
    if _TIMEOUT_TEXT_RX.search(text):
        return True
    if classify_failure(text) is not False:
        return True
    # confidently transient: budget the escape (one retry opportunity, per the stop_text).
    key = (last.get("name", ""), _pairing_input(last.get("input")))
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
    return transients >= 2


def _pairing_input(inp) -> str:
    """`canon_input` with leading-dunder keys dropped — the call-identity fold used to pair a
    PostToolUse back to its own PreToolUse AND (since the ADR 0024 follow-up) as the per-key
    verdict identity inside this module's own sequence primitives (`recur_stuck`,
    `timed_out_at_turn_end`'s transient budget).

    A harness may add bookkeeping keys to `tool_input` BETWEEN a call's Pre and its Post, so
    pairing on the FULL canonical input would leave a dangling Pre for a call that in fact
    succeeded. See docs/adr/0024-dunder-insensitive-call-pairing.md for the decision history.
    The SAME injection class also broke the verdict side while it keyed on the full
    `canon_input`: a bookkeeping key that VARIES per call (`__seq`) split a byte-identical
    retry loop into distinct keys, so recur never saw a run of length >= 2.

    A leading `__` is a transport/bookkeeping convention, never call semantics, so dropping it
    cannot collapse two genuinely distinct calls — for pairing or for a verdict. Primitives in
    OTHER modules (`identical_retry`) still key on their own folds."""
    if isinstance(inp, dict):
        return canon_input({k: v for k, v in inp.items() if not str(k).startswith("__")})
    return canon_input(inp)


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


# =============================================================================================
# Stop-hook adapter (formerly stopchecks/stopcheck_canon.py)
# =============================================================================================
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


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.canon", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="CLAIM_VS_HISTORY",
               eats=frozenset({"history", "transcript_path", "session_id", "state_root"}),
               run=lambda c: canon_gate(c.history, transcript_path=c.transcript_path,
                                         session_id=c.session_id, state_root=c.state_root))
