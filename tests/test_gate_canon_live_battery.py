"""Anti-Goodhart contamination battery for gate.canon -- through the LIVE run_stop_checks path.

canon.timeout / canon.recur are ported, never-before-live Stop primitives (from the read-only
ancestor makoto-dev). The ancestor's own held-out-validation test
(tests/canon/test_recur_heldout_validation.py) measured that the real historical corpus almost
never carries `interrupted=True` / a self_error_code at all -- so a 0-FP corpus replay alone is
INCONCLUSIVE, not a certification: a check that only ever goes green on the honest corpus has
never been shown to discriminate anything (the near-vacuous-precondition problem). This battery
supplies the missing RED side explicitly, in-repo, hand-authored (CLAUDE.md multi-layer
reliability canaries / anti-Goodhart), mirroring test_gate_dropped_live_battery.py's discipline:

  * a TP ("held-out RED") population of hand-authored adversarial call streams that MUST every one
    fire -- a silent TP VOIDS the battery (assert-fails loudly), it does not quietly pass.
  * a TN population of adjacent near-misses -- drawn directly from each primitive's own documented
    silencing rule -- that MUST every one stay silent. Any fire is a measured false positive.
  * a "Law 1" pair of tests proving the discriminating precondition (the agnostic terminal state
    each primitive actually reads) is PRESENT on every RED fixture and ABSENT on every TN/clean
    fixture -- the missing half a corpus-only measurement can never supply for itself.

All three populations route through `makoto._dispatch.run_stop_checks` -- the SAME function
`makoto._dispatch.main()` calls for a real Stop event -- with hand-built events-table row tuples
`(id, ts, event_type, cwd, raw_payload_json)` matching the exact shape `_select_recent` returns
(not a weaker reimplementation), so a discharge/wiring regression the pure-function unit tests
(test_canon_primitives.py) would miss reddens here too.
"""
import json
import sqlite3

from makoto._dispatch import run_stop_checks
from makoto.checks.canonTimeoutRecur import calls_from_history, recur_stuck, timed_out_at_turn_end

_COMMIT_DDL = (
    "CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
    "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
    "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
_LEDGER_DDL = (
    "CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
    "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")


def _conn():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute(_COMMIT_DDL)
    c.execute(_LEDGER_DDL)
    return c


def _row(idx, cwd, tool_name, tool_input, tool_response, event_type="PostToolUse"):
    """One events-table row tuple in the REAL shape `_select_recent` returns: (id, ts, event_type,
    cwd, raw_payload_json)."""
    payload = json.dumps({
        "hook_event_name": event_type,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
    })
    return (idx, f"2026-07-05T00:00:{idx:02d}.000Z", event_type, cwd, payload)


def _canon_messages(history, cwd, *, text="Done for now."):
    """Drive `history` through the real wired Stop path and return every gate.canon Finding's
    message (each prefixed "canon.<id>: " by the adapter -- see stopcheck_canon.py)."""
    conn = _conn()
    out = run_stop_checks(conn, {"last_assistant_message": text, "session_id": "s", "cwd": cwd}, history)
    conn.close()
    return [f.message for f in out if getattr(f, "pattern_id", "") == "gate.canon"]


# ---- RED population: MUST every one fire ---------------------------------------------------------
def test_red_unresolved_interrupted_call_at_turn_end_fires_canon_timeout(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "long-thing"}, {"interrupted": True})]
    msgs = _canon_messages(history, cwd)
    assert any(m.startswith("canon.timeout:") for m in msgs), \
        f"canon.timeout MUST fire on an unresolved interrupted last call -- battery VOID: {msgs}"


def test_red_unresolved_self_error_code_call_at_turn_end_fires_canon_timeout(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "thing"}, {"error": "E_TIMEOUT"})]
    msgs = _canon_messages(history, cwd)
    assert any(m.startswith("canon.timeout:") for m in msgs), \
        f"canon.timeout MUST fire on a self_error_code last call -- battery VOID: {msgs}"


def test_red_two_consecutive_identical_failing_calls_fires_canon_recur(tmp_path):
    cwd = str(tmp_path)
    ti = {"command": "flaky-thing"}
    history = [
        _row(1, cwd, "Bash", ti, {"interrupted": True}),
        _row(2, cwd, "Bash", ti, {"interrupted": True}),
    ]
    msgs = _canon_messages(history, cwd)
    assert any(m.startswith("canon.recur:") for m in msgs), \
        f"canon.recur MUST fire on 2 consecutive identical failing calls -- battery VOID: {msgs}"


def test_red_three_consecutive_identical_failing_calls_still_fires_canon_recur(tmp_path):
    cwd = str(tmp_path)
    ti = {"command": "flaky-thing"}
    history = [_row(i, cwd, "Bash", ti, {"error": "E1"}) for i in range(1, 4)]
    msgs = _canon_messages(history, cwd)
    assert any(m.startswith("canon.recur:") for m in msgs), \
        f"canon.recur MUST fire on a 3-run of identical failing calls -- battery VOID: {msgs}"


# ---- TN population: MUST every one stay silent ----------------------------------------------------
def test_tn_recur_and_timeout_silent_when_the_run_ends_in_success(tmp_path):
    """The same identical-retry shape as the RED recur fixture, but the LAST occurrence succeeds --
    recur's run-end judgment resolves it, and timeout's last-call check is also clean."""
    cwd = str(tmp_path)
    ti = {"command": "flaky-thing"}
    history = [
        _row(1, cwd, "Bash", ti, {"interrupted": True}),
        _row(2, cwd, "Bash", ti, {"stdout": "ok", "stderr": ""}),
    ]
    msgs = _canon_messages(history, cwd)
    assert not any(m.startswith("canon.recur:") for m in msgs), \
        f"canon.recur FALSE-POSITIVE: a run resolved by a later success must stay silent: {msgs}"
    assert not any(m.startswith("canon.timeout:") for m in msgs), \
        f"canon.timeout FALSE-POSITIVE: the last call succeeded: {msgs}"


def test_tn_timeout_silent_when_a_later_different_call_succeeds(tmp_path):
    """An error occurs mid-turn but a LATER, DIFFERENT, successful call closes the turn -- only the
    true final call matters to canon.timeout."""
    cwd = str(tmp_path)
    history = [
        _row(1, cwd, "Bash", {"command": "flaky-thing"}, {"interrupted": True}),
        _row(2, cwd, "Bash", {"command": "different-thing"}, {"stdout": "ok", "stderr": ""}),
    ]
    msgs = _canon_messages(history, cwd)
    assert not any(m.startswith("canon.timeout:") for m in msgs), \
        f"canon.timeout FALSE-POSITIVE: a resolved-then-fixed error must stay silent: {msgs}"


def test_tn_recur_silent_when_inputs_differ_even_though_both_error(tmp_path):
    """Two calls with the SAME tool_name but DIFFERENT tool_input, both erroring -- not
    byte-identical, so recur must stay silent (canon.timeout legitimately still fires here since
    the last call errored -- not asserted either way, per the ancestor's own isolation discipline)."""
    cwd = str(tmp_path)
    history = [
        _row(1, cwd, "Bash", {"command": "thing-a"}, {"interrupted": True}),
        _row(2, cwd, "Bash", {"command": "thing-b"}, {"interrupted": True}),
    ]
    msgs = _canon_messages(history, cwd)
    assert not any(m.startswith("canon.recur:") for m in msgs), \
        f"canon.recur FALSE-POSITIVE: differing tool_input is not byte-identical: {msgs}"


def test_tn_recur_silent_on_a_single_interrupted_call_with_no_retry(tmp_path):
    """A single (non-consecutive-repeated) interrupted call with no retry -- recur needs a run of
    >=2, so it must stay silent (canon.timeout legitimately still fires: it IS the last call --
    not asserted either way)."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "thing"}, {"interrupted": True})]
    msgs = _canon_messages(history, cwd)
    assert not any(m.startswith("canon.recur:") for m in msgs), \
        f"canon.recur FALSE-POSITIVE: a single call is never a retry loop: {msgs}"


def test_tn_recur_silent_when_a_different_call_intervenes(tmp_path):
    """The identical failing call recurs, but a DIFFERENT call breaks the consecutive run --
    recur must stay silent."""
    cwd = str(tmp_path)
    ti = {"command": "flaky-thing"}
    history = [
        _row(1, cwd, "Bash", ti, {"interrupted": True}),
        _row(2, cwd, "Read", {"file_path": "a.txt"}, {"stdout": "text"}),
        _row(3, cwd, "Bash", ti, {"interrupted": True}),
    ]
    msgs = _canon_messages(history, cwd)
    assert not any(m.startswith("canon.recur:") for m in msgs), \
        f"canon.recur FALSE-POSITIVE: a different intervening call breaks the run: {msgs}"


def test_clean_successful_history_nothing_fires(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "ls"}, {"stdout": "a\nb", "stderr": ""})]
    assert _canon_messages(history, cwd) == []


def test_empty_history_nothing_fires(tmp_path):
    cwd = str(tmp_path)
    assert _canon_messages([], cwd) == []


# ---- Law 1: the discriminating precondition is present on every RED, absent on every TN/clean ----
def test_law1_timeout_precondition_present_on_red_absent_on_tn_and_clean(tmp_path):
    """Proves timed_out_at_turn_end's own agnostic precondition (the LAST decoded call is
    interrupted/self_error_code) actually holds on the RED fixtures above and is absent on the
    TN/clean ones -- the explicit RED-side proof a corpus-FP-only measurement can never supply."""
    cwd = str(tmp_path)
    red_histories = [
        [_row(1, cwd, "Bash", {"command": "long-thing"}, {"interrupted": True})],
        [_row(1, cwd, "Bash", {"command": "thing"}, {"error": "E_TIMEOUT"})],
    ]
    silent_histories = [
        [_row(1, cwd, "Bash", {"command": "flaky-thing"}, {"interrupted": True}),
         _row(2, cwd, "Bash", {"command": "different-thing"}, {"stdout": "ok"})],
        [_row(1, cwd, "Bash", {"command": "ls"}, {"stdout": "a\nb"})],
        [],
    ]
    for hist in red_histories:
        assert timed_out_at_turn_end(calls_from_history(hist)) is True, \
            "RED fixture must carry canon.timeout's discriminating precondition"
    for hist in silent_histories:
        assert timed_out_at_turn_end(calls_from_history(hist)) is False, \
            "TN/clean fixture must NOT carry canon.timeout's discriminating precondition"


def test_law1_recur_precondition_present_on_red_absent_on_tn_and_clean(tmp_path):
    """Same proof for recur_stuck's own precondition (a run of >=2 consecutive identical-key calls,
    every one in a no-info error state)."""
    cwd = str(tmp_path)
    ti = {"command": "flaky-thing"}
    red_histories = [
        [_row(1, cwd, "Bash", ti, {"interrupted": True}),
         _row(2, cwd, "Bash", ti, {"interrupted": True})],
    ]
    silent_histories = [
        [_row(1, cwd, "Bash", ti, {"interrupted": True}),
         _row(2, cwd, "Bash", ti, {"stdout": "ok"})],                          # run ends in success
        [_row(1, cwd, "Bash", {"command": "thing-a"}, {"interrupted": True}),
         _row(2, cwd, "Bash", {"command": "thing-b"}, {"interrupted": True})],  # differing input
        [_row(1, cwd, "Bash", ti, {"interrupted": True})],                     # single, no retry
        [],
    ]
    for hist in red_histories:
        assert recur_stuck(calls_from_history(hist)) is True, \
            "RED fixture must carry canon.recur's discriminating precondition"
    for hist in silent_histories:
        assert recur_stuck(calls_from_history(hist)) is False, \
            "TN/clean fixture must NOT carry canon.recur's discriminating precondition"
