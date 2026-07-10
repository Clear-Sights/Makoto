"""Falsifying tests for the decode-layer extension (this ticket): permission_mode / agent_id /
agent_type must become OBSERVABLE on GateContext, additive-only (existing fields/behavior
untouched), and wired end-to-end from the raw hook payload via `run_stop_checks`.

Field-name grounding (not guesses): `permission_mode`, `agent_id`, `agent_type` are documented,
confirmed-real, top-level fields on every Claude Code hook payload (hooks reference, fetched
2026-07-06). No literal `isSubAgent`/`isSidechain`/`permissionMode` (camelCase) field exists in
the documented schema — `agent_id` presence is the real, grounded substrate for "is this a
subagent", surfaced here as the derived `GateContext.is_subagent` convenience.
"""
import sqlite3

import makoto._dispatch as _dispatch
from makoto.substrate._loader import Check
from makoto.substrate._shared import GateContext


def _setup_state(tmp_path):
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n")
    init_db(state_dir, citations)
    return state_dir


# ---- GateContext itself: additive fields, safe defaults ---------------------------------------
def test_gate_context_permission_agent_fields_default_none_and_not_subagent():
    ctx = GateContext(text="x", touched=frozenset(), empty=frozenset(), opens=[],
                       testrun_output="", cwd="/tmp",
                       fs_exists=lambda p: False, fs_size=lambda p: None, fs_read=lambda p: None)
    assert ctx.permission_mode is None
    assert ctx.agent_id is None
    assert ctx.agent_type is None
    assert ctx.is_subagent is False


def test_gate_context_carries_permission_agent_fields_when_set():
    ctx = GateContext(text="x", touched=frozenset(), empty=frozenset(), opens=[],
                       testrun_output="", cwd="/tmp",
                       fs_exists=lambda p: False, fs_size=lambda p: None, fs_read=lambda p: None,
                       permission_mode="plan", agent_id="agent-123", agent_type="Explore")
    assert ctx.permission_mode == "plan"
    assert ctx.agent_id == "agent-123"
    assert ctx.agent_type == "Explore"
    assert ctx.is_subagent is True


# ---- end-to-end: run_stop_checks decodes the raw payload onto the built GateContext ------------
def _spy_stopcheck(sink: list):
    def _run(ctx):
        sink.append(ctx)
        return None
    return Check(id="test.spy", applies_at="Stop", posture="BLOCK", run=_run)


def test_run_stop_checks_extracts_permission_mode_and_agent_fields_from_payload(tmp_path, monkeypatch):
    state_dir = _setup_state(tmp_path)
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    captured: list = []
    monkeypatch.setattr(_dispatch, "load_checks", lambda edge=None: [_spy_stopcheck(captured)])
    payload = {
        "hook_event_name": "Stop", "session_id": "s1", "cwd": str(tmp_path),
        "last_assistant_message": "done.",
        "permission_mode": "acceptEdits", "agent_id": "sub-1", "agent_type": "security-reviewer",
    }
    _dispatch.run_stop_checks(conn, payload, history=())
    conn.close()
    assert len(captured) == 1
    ctx = captured[0]
    assert ctx.permission_mode == "acceptEdits"
    assert ctx.agent_id == "sub-1"
    assert ctx.agent_type == "security-reviewer"
    assert ctx.is_subagent is True


def test_run_stop_checks_leaves_fields_none_when_payload_omits_them(tmp_path, monkeypatch):
    state_dir = _setup_state(tmp_path)
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    captured: list = []
    monkeypatch.setattr(_dispatch, "load_checks", lambda edge=None: [_spy_stopcheck(captured)])
    payload = {
        "hook_event_name": "Stop", "session_id": "s2", "cwd": str(tmp_path),
        "last_assistant_message": "done.",
    }
    _dispatch.run_stop_checks(conn, payload, history=())
    conn.close()
    assert len(captured) == 1
    ctx = captured[0]
    assert ctx.permission_mode is None
    assert ctx.agent_id is None
    assert ctx.agent_type is None
    assert ctx.is_subagent is False
