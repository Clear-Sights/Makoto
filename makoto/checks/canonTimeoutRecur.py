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

ADAPTATION NOTE (the substrate divergence from the ancestor, revised for FD14-A): the ancestor's
`calls_from_history` turned every PreToolUse OR PostToolUse row into a Call. Live makoto's real
events table (see `makoto/dispatch.py::_ingest_event` / `_select_recent`) stores EVERY hook
payload verbatim, including a PreToolUse row fired BEFORE the tool runs (so its `tool_response`
is always absent/empty) as a SEPARATE row from the PostToolUse row fired after (carrying the
actually-resolved result) for the very same call. Decoding both naively would insert a spurious
result={} Call ahead of every real result: two consecutive identical failing Bash calls would
decode as [Pre(no-err), Post(err), Pre(no-err), Post(err)] — never a run of >=2 consecutive
same-key ALL-err calls — silently defeating `recur_stuck` against the real substrate. So
`calls_from_history` PAIRS each PostToolUse to the nearest preceding still-unpaired identical
PreToolUse and keeps only the PostToolUse Call for a completed call — the paired Pre is dropped.

FD14-A (scope narrowed by owner decision, see EXECUTION_PLAN.md / SPEC-4 Task 2 — MID-TURN
ABANDONMENT ONLY): a leftover unpaired PreToolUse is a dangling Pre. NOT every dangling Pre is a
failure signal — `test_dispatch_fabricated_action_silent_when_command_ran` (test_dispatch.py) pins
that a SINGLE dangling Pre that is the LAST tool-related row before Stop must mean "presence of
work, discharge the claim" and must stay silent, not fail. FD14-A's actual target is narrower:
mid-turn abandonment, where a tool call was fired, never resolved, and the agent moved on to
something else anyway (another Pre or Post, for any tool) before Stop. So a dangling Pre
synthesizes a FAILURE Call (result `{"interrupted": True, "error": ...}`) at its original position
ONLY IF some OTHER decoded row — Pre or Post, any tool — occurs at a LATER index in the decoded
history than this dangling Pre. If the dangling Pre is the last decoded row overall, it is left
out entirely, matching the pre-FD14-A/unmodified behavior for that shape (no Call is synthesized,
so `timed_out_at_turn_end` reads whatever real call preceded it, exactly as before this ticket).

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
from typing import Iterable, List

from makoto.vocab import Finding
from makoto.kit import classify_failure, decode_history_event, failure_terminal_result

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
    """agnostic terminal `self_error_code`: a harness-emitted error code/object on the result."""
    return _result(c).get("error") or _result(c).get("error_code")


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
    normal, not a timeout — exit_code buys no true positive here and costs false ones)."""
    return interrupted(c) or bool(self_error_code(c))


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
    def _no_info_err(c) -> bool:
        return interrupted(c) or bool(self_error_code(c))

    def _transient_err(c) -> bool:
        error = self_error_code(c)
        return _no_info_err(c) and error is not None and classify_failure(str(error)) is False

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
        key = (c.get("name", ""), _canon_input(c.get("input")))
        call_err = _no_info_err(c)
        call_transient = _transient_err(c)
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


def timed_out_at_turn_end(calls: list) -> bool:
    """canon.timeout: the turn CLOSED on an UNRESOLVED direct error — the LAST decoded call before
    Stop is in a direct error state (`timed_out`: interrupted or self_error_code).

    Sequence-level, NOT per-call EXISTS: the signal is "left unresolved AT TURN-END", not "an
    error occurred somewhere in the turn". A call that errored but was RESOLVED before the turn
    closed — a later call succeeded, e.g. a flaky command re-run that finally passed — is not a
    silent unresolved error, so it stays silent. Likewise, one non-interrupted failure whose error
    text is confidently transient is a recoverable blip, not an unresolved-error turn end. An
    explicit harness interruption still fires even when its accompanying text sounds transient;
    deterministic and uncertain errors retain the ordinary one-call bar."""
    if not calls:
        return False
    last = calls[-1]
    if interrupted(last):
        return True
    error = self_error_code(last)
    return bool(error) and classify_failure(str(error)) is not False


def _canon_input(inp) -> str:
    """A stable, identity-comparable serialization of a tool_input dict (key order-independent).
    Used ONLY to compare two calls for byte-identity — it reads no content semantically."""
    try:
        return json.dumps(inp, sort_keys=True, default=str)
    except Exception:
        return repr(inp)


def _pairing_input(inp) -> str:
    """`_canon_input` with leading-dunder keys dropped — the identity used ONLY to pair a
    PostToolUse back to its own PreToolUse, never to judge a verdict.

    A harness may add bookkeeping keys to `tool_input` BETWEEN a call's Pre and its Post, so
    pairing on the FULL canonical input would leave a dangling Pre for a call that in fact
    succeeded. See docs/adr/0024-dunder-insensitive-call-pairing.md for the decision history.

    A leading `__` is a transport/bookkeeping convention, never call semantics, so dropping it
    cannot collapse two genuinely distinct calls. This RELAXES PAIRING ONLY: `recur_stuck`,
    `identical_retry` and every other primitive keep keying on the full `_canon_input`, so the
    verdict's identity test is untouched and no true positive is widened away."""
    if isinstance(inp, dict):
        return _canon_input({k: v for k, v in inp.items() if not str(k).startswith("__")})
    return _canon_input(inp)


# ---- the history -> Call adapter (protocol-field decode; fail-open per row) -------------------
def _decode_row(row):
    """Decode ONE history row into (etype, name, input_dict, result_dict), or None to skip.

    Raw decode + wrapper-event-type fallback is `kit.decode_history_event` -- the canonical
    step, shared with `identicalRetryInterdiction._most_recent_completed_bash_call`. This
    function keeps only what's specific to canon's OWN adapter shape: the tuple conversion, and
    keeping PreToolUse plus both settled terminal events (unlike the pre-FD14-A cut which dropped
    Pre at decode time) so `calls_from_history` can pair them and detect a dangling Pre.
    PostToolUseFailure is normalized to PostToolUse with its real top-level error/is_interrupt
    fields, so the existing pairing path treats it as the failed call's terminal."""
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
    """Decode GateContext.history rows into agnostic Call dicts carrying the protocol fields the
    terminals read. A completed call contributes a PreToolUse and either a PostToolUse or
    PostToolUseFailure row; each terminal is normalized to Post and PAIRED to the nearest
    preceding still-unpaired identical (tool name + `_pairing_input`) Pre, and only the terminal
    becomes a Call (the Pre is dropped) — so `recur_stuck`'s consecutive-run judgment is not
    corrupted by spurious result-less Calls (module docstring ADAPTATION NOTE).
    Pairing uses `_pairing_input` (dunder-insensitive), NOT the full `_canon_input` the verdicts
    key on: a harness may inject bookkeeping keys between a call's Pre and its Post, and pairing
    on those synthesized a phantom failure for a call that succeeded. See `_pairing_input`.

    FD14-A, narrowed to MID-TURN ABANDONMENT ONLY (see module docstring): a leftover unpaired
    PreToolUse (a dangling Pre) synthesizes a FAILURE Call — result `{"interrupted": True, ...}` —
    at its original position ONLY IF some OTHER decoded row (Pre or Post, any tool) sits at a
    LATER index in the decoded history than this dangling Pre, i.e. it is NOT the chronologically
    last tool-related row. A dangling Pre that IS the last decoded row is left out entirely (no
    Call synthesized), preserving `test_dispatch_fabricated_action_silent_when_command_ran`'s
    presence-of-work discharge. Fail-open per row (a malformed row is skipped, via `_decode_row`)."""
    decoded = [d for d in (_decode_row(r) for r in (history or ())) if d is not None]

    # pair each PostToolUse to the nearest PRECEDING still-unpaired identical PreToolUse.
    paired_pre: set = set()
    for j, (etype, name, ti, _tr) in enumerate(decoded):
        if etype != "PostToolUse":
            continue
        key = (name, _pairing_input(ti))
        for i in range(j - 1, -1, -1):
            if i in paired_pre:
                continue
            et2, n2, ti2, _ = decoded[i]
            if et2 == "PreToolUse" and (n2, _pairing_input(ti2)) == key:
                paired_pre.add(i)
                break

    last_index = len(decoded) - 1
    out: list = []
    for i, (etype, name, ti, tr) in enumerate(decoded):
        if etype == "PostToolUse":
            out.append({"name": name, "input": ti, "result": tr})
        elif i not in paired_pre and i != last_index:
            # dangling PreToolUse, NOT the last tool-related row before Stop -> mid-turn
            # abandonment: something else happened afterward and this call was still never
            # resolved. Synthesize the failure Call. (If i == last_index it is left silent —
            # presence-of-work discharge, see docstring.)
            out.append({"name": name, "input": ti, "result": {
                "interrupted": True,
                "error": "no PostToolUse for this PreToolUse (unresolved/failed tool call, "
                         "mid-turn abandonment)",
            }})
    return out


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
        # Task 0b part (a): the OLD hint said "...or state explicitly why the error is acceptable"
        # -- a discharge the detector cannot honor. timed_out_at_turn_end reads ONLY calls[-1]
        # (purely structural); prose can never change it. The two REAL discharges: a later
        # successful call (calls[-1] becomes non-error), or (Task 0b part b) a ledger-recorded
        # release.operator for a genuinely unresolvable, operator-surfaced block -- the same mechanism
        # gate.canon_fingerprints uses (makoto.state.ledger), not a third prose-only path.
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


def _release_clause(cid: str) -> str:
    """The `release.operator` affordance sentence for ONE primitive, generated from its id.

    `canon_gate` offers the ackblock discharge to EVERY fired primitive — the loop calls
    `find_ack_block(cid, ...)` for whatever fired, not just `timeout` — so every hint must name
    it: a mechanism that exists but is invisible reads exactly like a mechanism that is missing.
    See docs/adr/0025-per-primitive-release-affordance.md for the decision history.

    Generated per-id rather than written per-entry so a primitive cannot be added to
    CANON_SEQ_PRIMITIVES without carrying the discharge it is already wired to honor —
    the affordance is structural, not prose that the next author must remember to copy."""
    return (f" If this finding is a genuinely unresolvable, already-reviewed block — or a "
            f"misfire you have verified — say exactly `makoto release.operator {cid}: <reason>` "
            f"in a real (non-tool, non-quoted) reply; that is the only discharge other than "
            f"changing what the detector actually reads.")


def fired_primitives(history) -> Iterable:
    """Yield (canon_id, stop_text, retry_hint) for every installed primitive that fires on the
    session's call stream. Pure: no makoto import, no I/O beyond decoding the passed-in history
    rows. Every yielded hint carries its own `release.operator` clause (`_release_clause`) —
    `canon_gate` offers that discharge to every primitive, so every hint must name it."""
    calls = calls_from_history(history)
    for cid, (seq_pred, stop_text, retry_hint) in CANON_SEQ_PRIMITIVES.items():
        if seq_pred(calls):
            yield (cid, stop_text, retry_hint + _release_clause(cid))


# =============================================================================================
# Stop-hook adapter (formerly stopchecks/stopcheck_canon.py)
# =============================================================================================
def canon_gate(history, *, transcript_path=None, session_id=None, state_root=None) -> List[Finding]:
    """Fire one BLOCKING Finding per agnostic Canon primitive that matches the call stream, each
    stamped pattern_id="gate.canon" (so it actually blocks — see the module docstring's
    PATTERN_ID CONVENTION note) with the sub-primitive named at the front of its message
    ("canon.timeout: ..." / "canon.recur: ..."). Returns [] (silent) when no installed primitive
    fires — the discriminator's true-negative path.

    Task 0b part (b): canon.timeout has the SAME no-clean-terminal-state gap as
    gate.canon_fingerprints when the last error is a genuinely unresolvable, operator-surfaced
    block (a permission block the agent correctly declines to retry) -- text cannot change
    calls[-1], so without a real discharge it re-fires at every subsequent Stop. Reuses
    makoto.state.ledger's SAME transcript-re-derived, spoof-proof discharge (never trusted from
    chain content) -- one mechanism serving both gates, per SPEC-C's "one mercy model"."""
    out: List[Finding] = []
    for cid, stop_text, retry_hint in fired_primitives(history):
        ack = None
        try:
            import makoto.state.ledger as _ackblock
            ack = _ackblock.find_ack_block(cid, transcript_path=transcript_path,
                                           gate_pattern_id="gate.canon",
                                           session_id=session_id, root=state_root)
        except Exception:
            ack = None
        if ack is not None:
            try:
                _ackblock.record_ack_block_if_new(ack, session_id=session_id, root=state_root)
            except Exception:
                pass
            continue
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
