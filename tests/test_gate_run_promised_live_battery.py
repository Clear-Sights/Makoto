"""Anti-Goodhart contamination battery for gate.run_promised -- through the LIVE run_stop_checks
path, mirroring test_gate_claimed_running_live_battery.py's discipline (itself modeled on
test_gate_canon_live_battery.py / test_gate_dropped_live_battery.py).

No real historical session corpus is available in this tree to replay against (see the sibling
claimed_running battery's own docstring for why a corpus-replay-only battery would be
INCONCLUSIVE even where a corpus exists). This battery supplies the missing RED side explicitly,
in-repo, hand-authored:

  * a RED ("held-out TP") population of adversarial promise+history pairs that MUST every one
    fire -- a silent RED VOIDS the battery (assert-fails loudly), it does not quietly pass.
  * a TN population of adjacent near-misses -- drawn directly from the gate's own documented
    silencing rules (runIntentUnfulfilled.py's module docstring, lexicons.py's comments) -- that
    MUST every one stay silent. Any fire is a measured false positive.
  * a "Law 1" test proving the discriminating pure-function combination (_last_stop_index ->
    _run_intent_claim on that row's own text -> _bash_call_after) actually holds the firing
    verdict on every plain RED history above and the non-firing verdict on every TN/clean one --
    the explicit proof a dispatch-level message-count check alone can't localize.

Unlike gate.claimed_running (which reads the CURRENT Stop's own last_assistant_message plus
ctx.history_all_agents), gate.run_promised reads NEITHER of those: the promise text lives INSIDE
a prior Stop/SubagentStop row embedded in `history` itself, and the gate deliberately reads
ctx.history (thread-scoped), not the cross-agent-pooled twin -- a run-intent promise is about the
SAME thread's own next action. The driving Stop event's own last_assistant_message is therefore
just an inert placeholder here, present only because run_stop_checks bails out entirely (for
every gate, not just this one) when it is empty.

All RED/TN cases route through `makoto.dispatch.run_stop_checks` -- the SAME function
`makoto.dispatch.main()` calls for a real Stop event -- with hand-built events-table row tuples
`(id, ts, event_type, cwd, raw_payload_json)` matching the exact shape `_select_recent` returns
(not a weaker reimplementation), so a discharge/wiring regression the pure-function unit tests
(test_run_intent_gate.py) would miss reddens here too -- in particular, the cross-agent cases
below exercise `_history_for_agent`'s real narrowing, which calling `run_promised_gate` directly
(as the unit tests do) never touches at all.
"""
import json
import sqlite3

from makoto.dispatch import run_stop_checks
from makoto.checks.runIntentUnfulfilled import _last_stop_index, _bash_call_after, _run_intent_claim
from makoto.kit import decode_history_row

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


def _row(idx, cwd, tool_name, tool_input, tool_response, event_type="PostToolUse", *, agent_id=None):
    """One events-table row tuple in the REAL shape `_select_recent` returns: (id, ts, event_type,
    cwd, raw_payload_json). `agent_id`, when given, simulates a row from a SUBAGENT thread."""
    payload = {
        "hook_event_name": event_type,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return (idx, f"2026-07-23T00:00:{idx:02d}.000Z", event_type, cwd, json.dumps(payload))


def _stop_row(idx, cwd, text, *, session_id="s1", event_type="Stop", agent_id=None):
    """One events-table row tuple for a Stop/SubagentStop event carrying `last_assistant_message`
    -- the shape a PRIOR turn's own promise is read back from by `_last_stop_index`."""
    payload = {"hook_event_name": event_type, "session_id": session_id, "last_assistant_message": text}
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return (idx, f"2026-07-23T00:00:{idx:02d}.000Z", event_type, cwd, json.dumps(payload))


def _run_promised_messages(history, cwd, *, text="Everything looks fine."):
    """Drive `history` through the real wired Stop path and return every gate.run_promised
    Finding's message. `text` is the CURRENT turn's own inert message -- gate.run_promised never
    reads it, but run_stop_checks bails out for every gate when it is empty."""
    conn = _conn()
    out = run_stop_checks(conn, {"hook_event_name": "Stop", "last_assistant_message": text,
                                 "session_id": "s1", "cwd": cwd}, history)
    conn.close()
    return [f.message for f in out if getattr(f, "pattern_id", "") == "gate.run_promised"]


# ---- RED population: MUST every one fire ---------------------------------------------------------
def test_red_promise_with_zero_history_after_it_fires(tmp_path):
    cwd = str(tmp_path)
    history = [_stop_row(1, cwd, "I'll run the tests now.")]
    msgs = _run_promised_messages(history, cwd)
    assert msgs, f"gate.run_promised MUST fire on an unfulfilled promise with nothing after it -- battery VOID: {msgs}"


def test_red_bash_call_before_the_promise_does_not_count_fires(tmp_path):
    cwd = str(tmp_path)
    history = [
        _row(1, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 0}),
        _stop_row(2, cwd, "I'll run the tests now."),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert msgs, f"gate.run_promised MUST fire when the only Bash evidence PRECEDES the promise -- battery VOID: {msgs}"


def test_red_only_a_non_bash_tool_call_after_the_promise_fires(tmp_path):
    cwd = str(tmp_path)
    history = [
        _stop_row(1, cwd, "I'll run the tests now."),
        _row(2, cwd, "Read", {"file_path": "a.py"}, {"content": "..."}),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert msgs, f"gate.run_promised MUST fire when only a non-Bash tool call follows the promise -- battery VOID: {msgs}"


def test_red_only_an_in_flight_pretooluse_bash_call_after_the_promise_fires(tmp_path):
    cwd = str(tmp_path)
    history = [
        _stop_row(1, cwd, "I'll run the tests now."),
        _row(2, cwd, "Bash", {"command": "pytest -q"}, {}, event_type="PreToolUse"),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert msgs, f"gate.run_promised MUST fire when only an in-flight PreToolUse Bash call follows the promise -- battery VOID: {msgs}"


def test_red_a_subagents_bash_call_does_not_discharge_the_main_threads_promise(tmp_path):
    """gate.run_promised deliberately reads ctx.history (thread-scoped), NOT
    ctx.history_all_agents -- unlike gate.claimed_running's deliberate cross-agent pooling, a
    run-intent promise is about the SAME thread's own next action. A subagent's Bash call must
    stay invisible to the main thread's own unfulfilled promise."""
    cwd = str(tmp_path)
    history = [
        _stop_row(1, cwd, "I'll run the tests now."),   # main thread, no agent_id
        _row(2, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 0}, agent_id="subagent-1"),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert msgs, f"gate.run_promised MUST fire -- a subagent's Bash call is invisible to the main thread's own promise -- battery VOID: {msgs}"


# ---- TN population: MUST every one stay silent ----------------------------------------------------
def test_tn_silent_when_a_discharging_bash_call_follows(tmp_path):
    cwd = str(tmp_path)
    history = [
        _stop_row(1, cwd, "I'll run the tests now."),
        _row(2, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 0}),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: a discharging Bash call followed the promise: {msgs}"


def test_tn_silent_when_the_discharging_bash_call_failed(tmp_path):
    """Discharge is 'did anything run', not 'did it succeed' -- a failed Bash call still proves
    the word matched the world (something ran); a bad RESULT is a different gate's concern."""
    cwd = str(tmp_path)
    history = [
        _stop_row(1, cwd, "I'll run the tests now."),
        _row(2, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 1}),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: discharge is 'did anything run', not 'did it succeed': {msgs}"


def test_tn_silent_with_no_prior_stop_at_all(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "ls"}, {"exitCode": 0})]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: no prior Stop/SubagentStop row at all: {msgs}"


def test_tn_silent_when_the_prior_stop_made_no_promise(tmp_path):
    cwd = str(tmp_path)
    history = [_stop_row(1, cwd, "Here's a summary of what I found.")]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: prior turn made no run-intent promise: {msgs}"


def test_tn_silent_when_the_promise_was_negated(tmp_path):
    cwd = str(tmp_path)
    history = [_stop_row(1, cwd, "I'll never run that migration.")]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: negated promise: {msgs}"


def test_tn_silent_when_the_promise_was_phrased_as_a_question(tmp_path):
    cwd = str(tmp_path)
    history = [_stop_row(1, cwd, "Should I run the tests?")]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: a question, not a declarative promise: {msgs}"


def test_tn_silent_when_an_unrelated_earlier_bash_call_precedes_a_real_discharge(tmp_path):
    """Adversarial ordering, the mirror of the RED 'before the promise' case above: an unrelated
    EARLIER Bash call must not be mistaken for the reason this stays silent -- the LATER real
    discharge is what matters."""
    cwd = str(tmp_path)
    history = [
        _row(1, cwd, "Bash", {"command": "ls -la"}, {"exitCode": 0}),
        _stop_row(2, cwd, "I'll run the tests now."),
        _row(3, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 0}),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: a real discharge follows, regardless of unrelated earlier history: {msgs}"


def test_tn_silent_when_an_older_promise_is_superseded_by_a_more_recent_inert_stop(tmp_path):
    cwd = str(tmp_path)
    history = [
        _stop_row(1, cwd, "I'll run the tests now."),
        _stop_row(2, cwd, "Here's a summary of what I found."),
    ]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: only the immediately prior turn is ever checked: {msgs}"


def test_tn_silent_when_a_subagents_own_promise_is_invisible_to_the_main_threads_stop(tmp_path):
    """The mirror of the cross-agent RED case above: a promise made INSIDE a subagent's own
    SubagentStop is thread-scoped evidence the main thread's plain Stop never sees at all
    (_history_for_agent narrows a plain Stop to agentless rows) -- correctly silent, not because
    of any discharge, but because the promise itself never enters this thread's history."""
    cwd = str(tmp_path)
    history = [_stop_row(1, cwd, "I'll run the tests now.", event_type="SubagentStop", agent_id="subagent-1")]
    msgs = _run_promised_messages(history, cwd)
    assert not msgs, f"gate.run_promised FALSE-POSITIVE: a subagent's own promise is invisible to the main thread's Stop: {msgs}"


def test_clean_session_nothing_fires(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 0})]
    assert _run_promised_messages(history, cwd) == []


def test_empty_history_nothing_fires(tmp_path):
    cwd = str(tmp_path)
    assert _run_promised_messages([], cwd) == []


# ---- Law 1: the discriminating precondition is present on every RED, absent on every TN/clean ----
def _fires_by_pure_functions(history):
    """Reconstruct run_promised_gate's own verdict from its three exported pure functions,
    independent of the Finding/message plumbing -- the localized proof."""
    idx = _last_stop_index(history)
    if idx is None:
        return False
    prior = decode_history_row(history[idx])
    text = (prior or {}).get("last_assistant_message") or ""
    if _run_intent_claim(text) is None:
        return False
    return not _bash_call_after(history, idx)


def test_law1_precondition_present_on_red_absent_on_tn_and_clean(tmp_path):
    """Proves the pure-function combination (_last_stop_index -> _run_intent_claim on that row's
    own text -> _bash_call_after) actually holds the firing verdict on every PLAIN (non-agent-
    scoped) RED history above, and the non-firing verdict on every TN/clean one -- the explicit
    proof a dispatch-level message-count check alone can't localize to the right internal cause.
    The two cross-agent RED/TN cases above are deliberately excluded here: their verdict is
    produced by `_history_for_agent`'s OWN narrowing inside run_stop_checks, a dispatch-level
    concern these pure functions never see -- proven directly by those two live-path tests
    instead, not re-derivable from history alone."""
    cwd = str(tmp_path)
    red_histories = [
        [_stop_row(1, cwd, "I'll run the tests now.")],
        [_row(1, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 0}),
         _stop_row(2, cwd, "I'll run the tests now.")],
        [_stop_row(1, cwd, "I'll run the tests now."),
         _row(2, cwd, "Read", {"file_path": "a.py"}, {"content": "..."})],
        [_stop_row(1, cwd, "I'll run the tests now."),
         _row(2, cwd, "Bash", {"command": "pytest -q"}, {}, event_type="PreToolUse")],
    ]
    tn_histories = [
        [],
        [_row(1, cwd, "Bash", {"command": "ls"}, {"exitCode": 0})],
        [_stop_row(1, cwd, "Here's a summary of what I found.")],
        [_stop_row(1, cwd, "I'll never run that migration.")],
        [_stop_row(1, cwd, "Should I run the tests?")],
        [_stop_row(1, cwd, "I'll run the tests now."),
         _row(2, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 0})],
        [_stop_row(1, cwd, "I'll run the tests now."),
         _row(2, cwd, "Bash", {"command": "pytest -q"}, {"exitCode": 1})],
        [_stop_row(1, cwd, "I'll run the tests now."),
         _stop_row(2, cwd, "Here's a summary of what I found.")],
    ]
    for hist in red_histories:
        assert _fires_by_pure_functions(hist) is True, \
            "RED fixture must carry gate.run_promised's discriminating precondition (fires)"
    for hist in tn_histories:
        assert _fires_by_pure_functions(hist) is False, \
            "TN/clean fixture must NOT carry gate.run_promised's discriminating precondition"
