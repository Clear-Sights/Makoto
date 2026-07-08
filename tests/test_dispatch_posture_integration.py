"""SPEC-5 Task 8 integration pins: the posture cutover (`_dispatch._emit_decision` now folds a
fired finding through `makoto.posture`/`makoto.wire` instead of the old single ad-hoc
"decision":"block" shape). Three behavioral claims, one test each:

  1. a BLOCK precheck (PreToolUse) denies via the NEW nested Pre shape.
  2. a BLOCK Stop gate still blocks via the OLD top-level "decision":"block" shape (wire.py's
     Stop table renders that shape by construction -- this is deliberately unchanged).
  3. PostToolUse still runs refresh_if_stale/record_update with `citations.capture()` removed
     (no capture-shaped effect: a research-tool response's citations never land in
     canonical_citations, but the ledger `update` row and citations refresh still happen).
"""
import json
import sqlite3

from makoto.tests.test_dispatch import _setup_state, _run_dispatch


def test_pretooluse_block_renders_new_wire_shape(tmp_path):
    """PreCheck 1.1 (loose comparator) fires on PreToolUse -> the real Pre wire shape
    (hookSpecificOutput.permissionDecision == "deny"), not the old top-level "decision" key."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "posture_pre",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "constitution/integrity/checks/v.py",
            "content": 'def check(x):\n    return x.startswith("ok")\n',
        },
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert rc == 0
    assert out, "expected a deny body on stdout"
    body = json.loads(out)
    assert "decision" not in body, "Pre must not use the old ad-hoc top-level shape"
    assert body["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stop_gate_block_still_uses_old_top_level_shape(tmp_path):
    """gate.completion (a Stop gate) still renders {"decision": "block", ...} -- wire.py's
    Stop/SubagentStop table renders exactly that shape for a BLOCK outcome, so this is a
    no-op cutover for every existing Stop gate."""
    state_dir = _setup_state(tmp_path)
    stop = {
        "hook_event_name": "Stop",
        "session_id": "posture_stop",
        "cwd": str(tmp_path),
        "last_assistant_message": "Created src/promised_zzz.py. Done.",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "expected a block body on stdout"
    body = json.loads(out)
    assert body["decision"] == "block"
    assert body["hookEventName"] == "Stop"
    assert "src/promised_zzz.py" in body["reason"]


def test_posttooluse_still_refreshes_and_records_without_capture(tmp_path):
    """PostToolUse must still run refresh_if_stale (a canonical_citations row from CITATIONS.md
    exists) and record_update (a Write lands a ledger row), but a research-class tool's response
    (WebFetch) must NEVER seed canonical_citations now that capture() is gone."""
    state_dir = _setup_state(tmp_path)
    write = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "posture_post",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "src/x.py", "content": "pass\n"},
        "tool_response": {},
    }
    webfetch = {
        "hook_event_name": "PostToolUse",
        "tool_name": "WebFetch",
        "session_id": "posture_post",
        "cwd": str(tmp_path),
        "tool_input": {"url": "https://example.com"},
        "tool_response": "See Doe 2031 for details.",
    }
    rc1, out1 = _run_dispatch(state_dir, write)
    rc2, out2 = _run_dispatch(state_dir, webfetch)
    assert (rc1, out1) == (0, "")
    assert (rc2, out2) == (0, "")
    conn = sqlite3.connect(str(state_dir / "makoto.db"))
    try:
        cites = [r[0] for r in conn.execute("SELECT cite FROM canonical_citations").fetchall()]
        assert "Doe 2031" not in cites, (
            "capture() is removed -- a research tool_response must never seed canonical_citations"
        )
        assert cites, "refresh_if_stale must still have loaded CITATIONS.md's own citation(s)"
        ledger_rows = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        assert ledger_rows > 0, "record_update must still run on PostToolUse"
    finally:
        conn.close()
