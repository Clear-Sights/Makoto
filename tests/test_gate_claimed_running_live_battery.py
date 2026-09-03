"""Anti-Goodhart contamination battery for gate.claimed_running -- through the LIVE
run_stop_checks path, mirroring test_gate_canon_live_battery.py's discipline (itself modeled on
test_gate_dropped_live_battery.py).

No real historical session corpus is available in this tree to replay against: the "read-only
ancestor" repo that held lab/corpora + data/honest_corpus.json referenced by the canon battery's
own docstring is out of scope here, and even where such a corpus exists for a sibling gate, its
own held-out-validation work found the real corpus almost never carries a gate's own triggering
precondition at all (an unresolved process-start/healthcheck error is a rare event in an honest
transcript) -- so a 0-FP corpus replay alone would be INCONCLUSIVE, not a certification. A check
that only ever goes green on the honest corpus has never been shown to discriminate anything, only
that it doesn't cry wolf on silence. This battery supplies the missing RED side explicitly,
in-repo, hand-authored:

  * a TP ("held-out RED") population of adversarial claim+history pairs that MUST every one
    fire -- a silent TP VOIDS the battery (assert-fails loudly), it does not quietly pass.
  * a TN population of adjacent near-misses -- drawn directly from the gate's own documented
    silencing rules (claimedRunningAbsent.py's module docstring, lexicons.py's comments) -- that
    MUST every one stay silent. Any fire is a measured false positive.
  * a "Law 1" pair of tests proving the discriminating precondition
    (_latest_process_call_failed's own agnostic None/True/False verdict) actually holds on every
    RED history above and is the non-firing value on every TN/clean one -- the explicit pure-
    function proof a dispatch-level message-count check alone can't localize.

All RED/TN cases route through `makoto.dispatch.run_stop_checks` -- the SAME function
`makoto.dispatch.main()` calls for a real Stop event -- with hand-built events-table row tuples
`(id, ts, event_type, cwd, raw_payload_json)` matching the exact shape `_select_recent` returns
(not a weaker reimplementation), so a discharge/wiring regression the pure-function unit tests
(test_claimed_running_gate.py) would miss reddens here too.
"""
import json
import sqlite3

from makoto.dispatch import run_stop_checks
from makoto.checks.claimedRunningAbsent import _latest_process_call_failed

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
    cwd, raw_payload_json). `agent_id`, when given, simulates a row from a SUBAGENT thread --
    `_history_for_agent` narrows `ctx.history` to rows with NO agent_id (an agentless main-thread
    Stop), but `ctx.history_all_agents` pools these too (see claimedRunningAbsent.py's module
    docstring)."""
    payload = {
        "hook_event_name": event_type,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return (idx, f"2026-07-23T00:00:{idx:02d}.000Z", event_type, cwd, json.dumps(payload))


def _claimed_running_messages(history, cwd, *, text):
    """Drive `history` through the real wired Stop path and return every gate.claimed_running
    Finding's message."""
    conn = _conn()
    out = run_stop_checks(conn, {"hook_event_name": "Stop", "last_assistant_message": text,
                                 "session_id": "s", "cwd": cwd}, history)
    conn.close()
    return [f.message for f in out if getattr(f, "pattern_id", "") == "gate.claimed_running"]


_CLAIM = "I started the server. It is now running on port 3000."


# ---- RED population: MUST every one fire ---------------------------------------------------------
def test_red_no_process_lifecycle_evidence_at_all_fires(tmp_path):
    cwd = str(tmp_path)
    msgs = _claimed_running_messages([], cwd, text=_CLAIM)
    assert msgs, f"gate.claimed_running MUST fire on a running claim with zero recorded history -- battery VOID: {msgs}"


def test_vocabulary_miss_does_not_fire_through_the_real_dispatcher(tmp_path):
    """SUPERSEDES `test_red_only_unrelated_bash_history_fires`, which required a fire here. To a
    closed launcher net, "ran only unrelated commands" and "ran a launcher the net does not list"
    are ONE state, so requiring a fire required a false block on the second. Graded end-to-end
    through the real dispatcher so the silence is the shipped behaviour, not just the predicate's."""
    cwd = str(tmp_path)
    for cmd in ("ls -la", "air -c .air.toml", "php artisan serve"):
        history = [_row(1, cwd, "Bash", {"command": cmd}, {"stdout": "x", "exitCode": 0})]
        msgs = _claimed_running_messages(history, cwd, text=_CLAIM)
        assert not msgs, f"vocabulary miss must not block ({cmd}): {msgs}"


def test_red_no_bash_terminal_at_all_still_fires(tmp_path):
    """The teeth the supersession keeps: zero settled Bash terminals is the one genuinely
    ungrounded state, and it must still block through the real dispatcher."""
    cwd = str(tmp_path)
    msgs = _claimed_running_messages([], cwd, text=_CLAIM)
    assert msgs, f"gate.claimed_running MUST fire with no Bash evidence at all -- battery VOID: {msgs}"


def test_red_latest_launch_interrupted_fires(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"interrupted": True})]
    msgs = _claimed_running_messages(history, cwd, text=_CLAIM)
    assert msgs, f"gate.claimed_running MUST fire when the latest launch was interrupted -- battery VOID: {msgs}"


def test_red_latest_healthcheck_nonzero_exit_fires(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "curl -sf http://localhost:3000"}, {"exitCode": 7})]
    msgs = _claimed_running_messages(history, cwd, text="I started it earlier; it is still running.")
    assert msgs, f"gate.claimed_running MUST fire when the latest healthcheck exited non-zero -- battery VOID: {msgs}"


def test_red_post_tool_failure_without_exit_data_fires(tmp_path):
    """The terminal failure event has no exitCode/interrupted field; its event type is the
    evidence. This pins the PostToolUseFailure decoder arm used by live hooks."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {},
                    event_type="PostToolUseFailure")]
    msgs = _claimed_running_messages(history, cwd, text=_CLAIM)
    assert msgs, f"gate.claimed_running MUST fire on a PostToolUseFailure launch: {msgs}"


def test_red_latest_of_two_calls_is_the_failing_one_fires(tmp_path):
    """Adversarial ordering: an EARLIER clean launch, then a LATER failing healthcheck -- latest
    must win, proving this isn't merely 'was anything ever clean'."""
    cwd = str(tmp_path)
    history = [
        _row(1, cwd, "Bash", {"command": "npm run dev &"}, {"exitCode": 0}),
        _row(2, cwd, "Bash", {"command": "curl -sf http://localhost:3000"}, {"exitCode": 7}),
    ]
    msgs = _claimed_running_messages(history, cwd, text="I started the server. It is running now.")
    assert msgs, f"gate.claimed_running MUST fire when the LATEST recorded call is the failing one -- battery VOID: {msgs}"


# ---- TN population: MUST every one stay silent ----------------------------------------------------
def test_tn_silent_when_latest_launch_exited_cleanly(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"exitCode": 0})]
    msgs = _claimed_running_messages(history, cwd, text=_CLAIM)
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: a clean latest launch must stay silent: {msgs}"


def test_tn_silent_when_an_earlier_failure_is_superseded_by_a_later_clean_call(tmp_path):
    """Adversarial ordering, the mirror of the RED case above: a LATER clean call must supersede
    an EARLIER failure -- proving this is genuinely latest-wins, not merely 'any failure ever'."""
    cwd = str(tmp_path)
    history = [
        _row(1, cwd, "Bash", {"command": "npm run dev &"}, {"interrupted": True}),
        _row(2, cwd, "Bash", {"command": "curl -sf http://localhost:3000"}, {"exitCode": 0}),
    ]
    msgs = _claimed_running_messages(history, cwd, text="I started the server. It is running now.")
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: a later clean call must supersede an earlier failure: {msgs}"


def test_tn_silent_with_no_running_claim_at_all(tmp_path):
    cwd = str(tmp_path)
    msgs = _claimed_running_messages([], cwd, text="I started the server and configured the env file.")
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: no running-state language at all: {msgs}"


def test_tn_silent_without_a_first_person_start_verb(tmp_path):
    """The core FP the start-verb firewall exists for: generic explanatory prose about a tool's
    default behavior, paired with BAD history that would otherwise fire -- the claim signal itself
    must never ground on this text, regardless of history state."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"interrupted": True})]
    text = "Vite's dev server is running on port 5173 by default, no extra configuration needed."
    msgs = _claimed_running_messages(history, cwd, text=text)
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: generic explanatory prose, no first-person start verb: {msgs}"


def test_tn_silent_on_past_tense_admission(tmp_path):
    cwd = str(tmp_path)
    text = "I started the server. It was running fine until it crashed."
    msgs = _claimed_running_messages([], cwd, text=text)
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: past-tense 'was running' is not an ongoing-liveness claim: {msgs}"


def test_tn_silent_when_negated_in_the_same_clause(tmp_path):
    cwd = str(tmp_path)
    text = "I started the process. Honestly, I don't think it is running yet."
    msgs = _claimed_running_messages([], cwd, text=text)
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: negated in the same clause: {msgs}"


def test_tn_silent_when_the_only_mention_is_inside_a_code_span(tmp_path):
    cwd = str(tmp_path)
    text = "I started the server. The log line was `it is running` but I haven't actually checked."
    msgs = _claimed_running_messages([], cwd, text=text)
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: quoted/backticked mention, not the agent's own prose claim: {msgs}"


def test_tn_silent_when_a_subagent_launched_it_cleanly(tmp_path):
    """The cross-agent evidence fix (2026-07-23): a subagent dispatched to start the process is
    real session evidence -- the main thread's agentless Stop must see it via
    ctx.history_all_agents even though `_history_for_agent` would exclude this row from the
    thread-scoped ctx.history every other gate reads. Before the fix this false-fired
    UNFULFILLED on a true claim purely because a different thread made the launch call."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"exitCode": 0},
                    agent_id="subagent-1")]
    msgs = _claimed_running_messages(history, cwd, text="I started the server. It is running now.")
    assert not msgs, f"gate.claimed_running FALSE-POSITIVE: a subagent's clean launch is real session evidence: {msgs}"


def test_red_subagent_launch_interrupted_still_fires(tmp_path):
    """The mirror of the TN above, proving cross-agent pooling isn't a blanket silence: a
    subagent's INTERRUPTED launch must still ground the contradiction, exactly as a main-thread
    one would."""
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"interrupted": True},
                    agent_id="subagent-1")]
    msgs = _claimed_running_messages(history, cwd, text="I started the server. It is running now.")
    assert msgs, f"gate.claimed_running MUST fire when the subagent's own launch was interrupted -- battery VOID: {msgs}"


def test_clean_successful_history_nothing_fires(tmp_path):
    cwd = str(tmp_path)
    history = [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"stdout": "ready", "exitCode": 0})]
    assert _claimed_running_messages(history, cwd, text=_CLAIM) == []


def test_empty_history_no_claim_nothing_fires(tmp_path):
    cwd = str(tmp_path)
    assert _claimed_running_messages([], cwd, text="Everything looks good.") == []


# ---- Law 1: the discriminating precondition is present on every RED, absent on every TN/clean ----
def test_law1_precondition_present_on_red_absent_on_tn_and_clean(tmp_path):
    """Proves _latest_process_call_failed's own agnostic precondition actually holds the firing
    value (True, or None for zero grounding) on every history used by a RED fixture above, and the
    non-firing value (False) on every TN/clean history -- the explicit proof a dispatch-level
    message-count check alone can't localize to the right internal verdict."""
    cwd = str(tmp_path)
    red_true_histories = [
        [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"interrupted": True})],
        [_row(1, cwd, "Bash", {"command": "curl -sf http://localhost:3000"}, {"exitCode": 7})],
        [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"exitCode": 0}),
         _row(2, cwd, "Bash", {"command": "curl -sf http://localhost:3000"}, {"exitCode": 7})],
        [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {},
              event_type="PostToolUseFailure")],
    ]
    red_none_histories = [
        [],
    ]
    # NOT-EVALUABLE: a Bash terminal exists but matches no launcher in the closed net. This is
    # indistinguishable from a real unlisted launcher (`air`, `caddy run`), so it answers False
    # (silence), not None. It stays graded here rather than deleted -- the case is dispositioned,
    # not dropped.
    not_evaluable_histories = [
        [_row(1, cwd, "Bash", {"command": "ls -la"}, {"stdout": "a\nb", "exitCode": 0})],
        [_row(1, cwd, "Bash", {"command": "air -c .air.toml"}, {"exitCode": 0})],
    ]
    tn_false_histories = [
        [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"exitCode": 0})],
        [_row(1, cwd, "Bash", {"command": "npm run dev &"}, {"interrupted": True}),
         _row(2, cwd, "Bash", {"command": "curl -sf http://localhost:3000"}, {"exitCode": 0})],
    ]
    for hist in red_true_histories:
        assert _latest_process_call_failed(hist) is True, \
            "RED fixture must carry gate.claimed_running's discriminating precondition (True)"
    for hist in red_none_histories:
        assert _latest_process_call_failed(hist) is None, \
            "RED (no-evidence) fixture must show the precondition as None (ungrounded, not merely 'clean')"
    for hist in not_evaluable_histories:
        assert _latest_process_call_failed(hist) is False, \
            "vocabulary-miss fixture is NOT-EVALUABLE and must fall open (False), never fire"
    for hist in tn_false_histories:
        assert _latest_process_call_failed(hist) is False, \
            "TN/clean fixture must show the precondition as False (grounded AND clean)"
