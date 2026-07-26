"""SPEC-C item 1: the ledger table's rebuild-from-chain PROOF (docs/SPEC-C-REMAINING.md).
HOURGLASS VERIFY order -- lock the bar, PLANT the fault (delete the ledger table's rows), SEE
the query surface come back wrong/empty, THEN rebuild and see it match a pre-deletion snapshot
exactly.
"""
from __future__ import annotations

import sqlite3

from makoto.record import ledger
from makoto.record.db import init_db
from tests.rebuild_index import rebuild_ledger_table_from_chain


def _setup(tmp_path):
    state_dir = tmp_path / "state"
    (tmp_path / "CITATIONS.md").write_text("x")
    init_db(state_dir, tmp_path / "CITATIONS.md")
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"), isolation_level=None)
    return state_dir, conn


def _record(conn, state_dir, ev, event_id, session_id="s1"):
    ledger.record_update(conn, ev, event_id=event_id, session_id=session_id, root=state_dir)


def test_rebuild_restores_ledger_table_after_it_is_deleted(tmp_path):
    state_dir, conn = _setup(tmp_path)

    _record(conn, state_dir, {"hook_event_name": "PostToolUse", "tool_name": "Write",
                              "tool_input": {"file_path": "src/a.py", "content": "x" * 10}}, 1)
    _record(conn, state_dir, {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "pytest -q"},
                              "tool_response": {"stdout": "3 passed", "stderr": "", "exitCode": 0}}, 2)

    before_touched = ledger.read_key(conn, "src/a.py")
    before_testrun = ledger.latest_testrun(conn, "s1")
    assert before_touched is not None and before_testrun

    # PLANT the fault: the ledger table is gone (simulating "makoto.record.db deleted/corrupted").
    conn.execute("DELETE FROM ledger")
    conn.commit()
    assert ledger.read_key(conn, "src/a.py") is None                # SEE it fail first
    assert ledger.latest_testrun(conn, "s1") == ""

    replayed = rebuild_ledger_table_from_chain(conn, root=state_dir)
    assert replayed == 2

    after_touched = ledger.read_key(conn, "src/a.py")
    after_testrun = ledger.latest_testrun(conn, "s1")
    assert after_touched == before_touched
    assert after_testrun == before_testrun


def test_rebuild_never_reappends_to_the_chain_it_reads_from(tmp_path):
    state_dir, conn = _setup(tmp_path)
    _record(conn, state_dir, {"hook_event_name": "PostToolUse", "tool_name": "Write",
                              "tool_input": {"file_path": "a.py", "content": "x"}}, 1)
    rows_before = ledger.read(root=state_dir)
    conn.execute("DELETE FROM ledger")
    conn.commit()
    rebuild_ledger_table_from_chain(conn, root=state_dir)
    rows_after = ledger.read(root=state_dir)
    assert rows_after == rows_before, "a rebuild must be read-only against the chain"


def test_rebuild_only_replays_the_verified_prefix(tmp_path):
    """PLANT a tamper AFTER a real row -- the tampered row (and anything past it) must never be
    replayed, matching verify_chain's own trust boundary everywhere else it's read."""
    import json
    state_dir, conn = _setup(tmp_path)
    _record(conn, state_dir, {"hook_event_name": "PostToolUse", "tool_name": "Write",
                              "tool_input": {"file_path": "a.py", "content": "x"}}, 1)
    _record(conn, state_dir, {"hook_event_name": "PostToolUse", "tool_name": "Write",
                              "tool_input": {"file_path": "b.py", "content": "y"}}, 2)
    chain_file = state_dir / "chain.jsonl"
    lines = chain_file.read_text().splitlines()
    row1 = json.loads(lines[1])
    row1["value"] = "TAMPERED"
    lines[1] = json.dumps(row1, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    chain_file.write_text("\n".join(lines) + "\n")

    conn.execute("DELETE FROM ledger")
    conn.commit()
    replayed = rebuild_ledger_table_from_chain(conn, root=state_dir)
    assert replayed == 1                        # only row 0 (a.py) is within the verified prefix
    assert ledger.read_key(conn, "a.py") is not None
    assert ledger.read_key(conn, "b.py") is None


def test_rebuild_on_absent_chain_replays_zero_rows(tmp_path):
    state_dir, conn = _setup(tmp_path)
    assert rebuild_ledger_table_from_chain(conn, root=state_dir) == 0
