"""Unit tests for makoto.record.ledger.view_for / LedgerView — the unified read-surface facade
(SPEC-5 Task 2) every check (Tasks 3-9) will consume instead of hand-rolling its own SQL.

A thin FACADE, not new SQL: every LedgerView method delegates to this module's existing
module-level functions (touched_keys/empty_write_keys/latest_testrun/read_key), so this test
proves delegation (same result as calling the underlying function directly) rather than
re-proving the underlying SQL (already covered by test_ledger.py/test_ledger_reads.py).
"""
import sqlite3

from makoto.record import ledger
from makoto.record.ledger import view_for, LedgerView, record_update


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT, "
        "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)"
    )
    return c


def test_view_for_returns_a_ledger_view():
    c = _conn()
    v = view_for(c, "s1")
    assert isinstance(v, LedgerView)


def test_view_for_accepts_a_session_id_string():
    c = _conn()
    record_update(
        c, {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/auth.py", "content": "x"}},
        event_id=1, session_id="s1",
    )
    v = view_for(c, "s1")
    assert v.touched_keys() == ledger.touched_keys(c, "s1")
    assert "src/auth.py" in v.touched_keys()


def test_view_for_accepts_an_event_payload_dict():
    # "event_or_session": a raw hook payload dict carrying session_id works the same as a bare id.
    c = _conn()
    record_update(
        c, {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/auth.py", "content": "x"}},
        event_id=1, session_id="s1",
    )
    v = view_for(c, {"session_id": "s1", "hook_event_name": "Stop"})
    assert v.touched_keys() == {"src/auth.py"}


def test_view_for_missing_session_id_in_payload_is_empty_not_a_crash():
    c = _conn()
    v = view_for(c, {"hook_event_name": "Stop"})
    assert v.touched_keys() == set()


def test_empty_write_keys_delegates():
    c = _conn()
    record_update(
        c, {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/empty.py", "content": "   "}},
        event_id=1, session_id="s1",
    )
    v = view_for(c, "s1")
    assert v.empty_write_keys() == ledger.empty_write_keys(c, "s1")
    assert "src/empty.py" in v.empty_write_keys()


def test_latest_testrun_delegates():
    c = _conn()
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "pytest tests/x.py"},
          "tool_response": {"stdout": "1 passed", "stderr": "", "exitCode": 0}}
    record_update(c, ev, event_id=1, session_id="s1")
    v = view_for(c, "s1")
    assert v.latest_testrun() == ledger.latest_testrun(c, "s1")
    assert "1 passed" in v.latest_testrun()


def test_read_key_delegates():
    c = _conn()
    record_update(
        c, {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/auth.py", "content": "x"}},
        event_id=1, session_id="s1",
    )
    v = view_for(c, "s1")
    assert v.read_key("src/auth.py") == ledger.read_key(c, "src/auth.py")
    assert v.read_key("src/auth.py")["kind"] == "touched"


def test_existing_module_level_functions_are_unchanged_and_still_directly_callable():
    # Non-breaking guarantee: view_for is ADDITIVE. Every pre-existing caller
    # (_dispatch.py, stopchecks) keeps calling these bare functions unchanged.
    c = _conn()
    assert ledger.touched_keys(c, "nope") == set()
    assert ledger.empty_write_keys(c, "nope") == set()
    assert ledger.latest_testrun(c, "nope") == ""
    assert ledger.read_key(c, "nope") is None
