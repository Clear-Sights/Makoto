"""Regression for the 2026-07-20 cross-agent ``canon.recur`` latch.

The source-event ids below are all 141 real ``canon.recur`` audit fires from session
493b1e3d-c1a6-5dfa-b169-a7aaa78d258d, from 17:18:43.862968Z through 17:36:20.982380Z.  The audit
records preserve the firing edge but not raw hook payloads, so this fixture supplies the confirmed
thread identity shape: the dangling identical calls belong to one subagent and each stopping thread
has its own later activity.  Before the partition, every replay sees the pooled dangling calls.
"""
import json
import sqlite3

from makoto._dispatch import run_stop_checks


_REAL_FIRE_EVENT_IDS = (
    1913, 2036, 2095, 2106, 2107, 2122, 2188, 2198, 2202, 2210, 2218, 2237, 2238, 2254,
    2268, 2271, 2279, 2289, 2292, 2301, 2307, 2311, 2312, 2315, 2316, 2320, 2322, 2324,
    2325, 2328, 2331, 2332, 2333, 2338, 2340, 2346, 2347, 2351, 2352, 2354, 2360, 2364,
    2365, 2366, 2369, 2370, 2371, 2377, 2385, 2390, 2397, 2410, 2411, 2412, 2417, 2425,
    2426, 2429, 2430, 2431, 2442, 2444, 2445, 2447, 2450, 2453, 2461, 2462, 2463, 2467,
    2471, 2474, 2475, 2478, 2480, 2479, 2483, 2484, 2485, 2488, 2491, 2492, 2495, 2498,
    2500, 2501, 2502, 2507, 2508, 2520, 2538, 2541, 2542, 2545, 2565, 2568, 2571, 2576,
    2586, 2589, 2590, 2599, 2604, 2606, 2608, 2615, 2617, 2620, 2628, 2629, 2632, 2635,
    2640, 2641, 2642, 2643, 2646, 2647, 2650, 2651, 2652, 2653, 2654, 2657, 2658, 2659,
    2660, 2661, 2662, 2666, 2671, 2675, 2677, 2678, 2679, 2680, 2681, 2684, 2687, 2697,
    2700,
)
_REAL_MAIN_STOP_IDS = {
    1913, 2036, 2095, 2328, 2347, 2453, 2478, 2488, 2608, 2615, 2632, 2640, 2652,
}
_ABSENT = object()


def _conn():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
                 "location TEXT, qty_min REAL, qty_max REAL, status TEXT, retract_param TEXT, "
                 "created_event_id INTEGER, ts TEXT)")
    conn.execute("CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT, exit INTEGER, "
                 "source_event_id INTEGER, session_id TEXT, ts TEXT)")
    return conn


def _row(idx, event_type, tool_input, result, agent_id=_ABSENT):
    payload = {"hook_event_name": event_type, "tool_name": "Bash", "tool_input": tool_input}
    if event_type == "PostToolUse":
        payload["tool_response"] = result
    if agent_id is not _ABSENT:
        payload["agent_id"] = agent_id
    return (idx, f"2026-07-20T17:18:{idx % 60:02d}.000Z", event_type, "/repo",
            json.dumps(payload))


def _canon_recur(history, stop_payload):
    conn = _conn()
    try:
        findings = run_stop_checks(conn, stop_payload, history)
    finally:
        conn.close()
    return any(f.pattern_id == "gate.canon" and f.message.startswith("canon.recur:")
               for f in findings)


def _cross_agent_history(stopping_agent):
    repeated = {"command": "orphaned-call"}
    return [
        _row(1, "PreToolUse", repeated, {}, "dangling-agent"),
        _row(2, "PreToolUse", repeated, {}, "dangling-agent"),
        _row(3, "PostToolUse", {"command": "thread-finished"}, {"stdout": "ok"}, stopping_agent),
    ]


def test_real_141_cross_thread_fires_replay_to_zero():
    assert len(_REAL_FIRE_EVENT_IDS) == 141
    reproduced = []
    for event_id in _REAL_FIRE_EVENT_IDS:
        if event_id in _REAL_MAIN_STOP_IDS:
            stop = {"hook_event_name": "Stop", "session_id": "real-session",
                    "cwd": "/repo", "last_assistant_message": "Research complete."}
            stopping_agent = _ABSENT
        else:
            stopping_agent = f"recorded-subagent-{event_id}"
            stop = {"hook_event_name": "SubagentStop", "session_id": "real-session",
                    "cwd": "/repo", "last_assistant_message": "Research complete.",
                    "agent_id": stopping_agent}
        if _canon_recur(_cross_agent_history(stopping_agent), stop):
            reproduced.append(event_id)
    assert reproduced == [], f"cross-thread canon.recur replayed for {len(reproduced)}/141: {reproduced}"


def test_same_agent_genuinely_stuck_recur_still_fires():
    ti = {"command": "same-failing-call"}
    history = [
        _row(1, "PostToolUse", ti, {"interrupted": True}, "agent-a"),
        _row(2, "PostToolUse", ti, {"interrupted": True}, "agent-a"),
    ]
    stop = {"hook_event_name": "SubagentStop", "session_id": "s", "cwd": "/repo",
            "last_assistant_message": "Blocked.", "agent_id": "agent-a"}
    assert _canon_recur(history, stop) is True


def test_plain_main_stop_scopes_to_structurally_agentless_rows():
    ti = {"command": "main-loop-failure"}
    history = [
        _row(1, "PostToolUse", ti, {"error": "E"}),
        _row(2, "PostToolUse", ti, {"error": "E"}),
        _row(3, "PostToolUse", ti, {"stdout": "subagent"}, "agent-a"),
    ]
    stop = {"hook_event_name": "Stop", "session_id": "s", "cwd": "/repo",
            "last_assistant_message": "Blocked."}
    assert _canon_recur(history, stop) is True


def test_unknown_or_malformed_identity_never_pools_a_none_bucket():
    ti = {"command": "unknown-owner"}
    history = [_row(1, "PostToolUse", ti, {"error": "E"}),
               _row(2, "PostToolUse", ti, {"error": "E"})]
    ambiguous = [
        {"hook_event_name": "SubagentStop", "agent_id": None},
        {"hook_event_name": "SubagentStop"},
        {"hook_event_name": "Stop", "agent_id": ""},
        {"hook_event_name": "Stop", "agent_id": None},
    ]
    for payload in ambiguous:
        payload.update(session_id="s", cwd="/repo", last_assistant_message="Blocked.")
        assert _canon_recur(history, payload) is False
