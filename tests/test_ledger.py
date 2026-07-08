"""Unit tests for makoto.ledger — update recording + read-by-key.

Self-contained: builds its own in-memory `ledger` table (matches db.py schema),
so it does not depend on the DuckDB->SQLite migration. Uses REAL Bash
tool_response dict shape (stdout/stderr/exitCode), not a hand-built string.
"""
import sqlite3

from makoto.ledger import record_update, read_key


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT, "
        "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)"
    )
    return c


def test_write_records_touch():
    c = _conn()
    record_update(
        c,
        {"hook_event_name": "PostToolUse", "tool_name": "Write",
         "tool_input": {"file_path": "src/auth.py"}},
        event_id=7, session_id="s",
    )
    row = read_key(c, "src/auth.py")
    assert row is not None
    assert row["kind"] == "touched"
    assert row["source_event_id"] == 7


def test_retest_supersedes_no_fire():
    c = _conn()
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "pytest tests/x.py"},
          "tool_response": {"stdout": "3 passed", "stderr": "", "exitCode": 0}}
    record_update(c, ev, event_id=1, session_id="s")
    ev2 = {**ev, "tool_response": {"stdout": "10 passed", "stderr": "", "exitCode": 0}}
    record_update(c, ev2, event_id=2, session_id="s")
    row = read_key(c, "tests/x.py")
    assert row is not None
    assert "10 passed" in (row["value"] or "")     # latest-wins, no second row
    assert row["source_event_id"] == 2
    n = c.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
    assert n == 1


def test_unknown_key_returns_none():
    assert read_key(_conn(), "never/touched.py") is None


def test_bash_key_fallback_to_cwd():
    # No path-shaped token in the command -> _bash_key must fall back to the
    # normalized cwd (line 26). Pins RETURN->None: if _bash_key returned None,
    # the row is keyed NULL and read_key('/some/dir') would miss it.
    c = _conn()
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "echo hello"},
          "cwd": "/some/dir",
          "tool_response": {"stdout": "hello", "stderr": "", "exitCode": 0}}
    record_update(c, ev, event_id=1, session_id="s")
    row = read_key(c, "/some/dir")
    assert row is not None
    assert row["kind"] == "value"


def test_bash_key_fallback_to_bash_constant():
    # No path token and no cwd -> _bash_key must fall back to the 'bash'
    # constant via `normalize_path(...) or 'bash'` (line 26). Pins BOOL or->and:
    # `and` would yield '' (empty key) and read_key('bash') would miss the row.
    c = _conn()
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "true"},
          "tool_response": {"stdout": "", "stderr": "", "exitCode": 0}}
    record_update(c, ev, event_id=1, session_id="s")
    row = read_key(c, "bash")
    assert row is not None
    assert row["kind"] == "value"


# === A2: test-runner output is filed under kind='testrun' (the green-claim gate's source) =====

def test_testrun_command_files_kind_testrun():
    """a pytest command's output -> kind='testrun' (so green_claim_gate consults it)."""
    c = _conn()
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "python -m pytest tests/ -q"},
          "tool_response": {"stdout": "=== 3 failed, 678 passed in 12.3s ===", "stderr": "",
                            "exitCode": 1}}
    record_update(c, ev, event_id=1, session_id="s")
    row = read_key(c, "bash")                    # no '.ext' path token in cmd -> 'bash' key
    assert row is not None
    assert row["kind"] == "testrun"
    assert "3 failed" in (row["value"] or "")


def test_non_runner_failing_output_stays_value():
    """THE cat-a-log firewall: a non-runner command that PRINTS a failure summary is kind='value',
    NOT 'testrun' — so green_claim_gate never reads it. Caught the open-world FP of B at the source."""
    c = _conn()
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "cat tests/old_run.log"},
          "tool_response": {"stdout": "=== 3 failed, 678 passed in 12.3s ===", "stderr": "",
                            "exitCode": 0}}
    record_update(c, ev, event_id=1, session_id="s")
    row = read_key(c, "tests/old_run.log")
    assert row is not None
    assert row["kind"] == "value"            # NOT 'testrun' — the firewall


def test_testrun_stores_verdict_tail_not_head():
    """the pass/fail verdict lives at the END of pytest output; testrun rows store the TAIL so a
    long head (collection noise) never truncates the verdict away."""
    c = _conn()
    head = "x" * 2000                                            # long collection/progress noise
    verdict = "\n=========== 2 failed, 5 passed in 3.1s ==========="
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "pytest -q"},
          "tool_response": {"stdout": head + verdict, "stderr": "", "exitCode": 1}}
    record_update(c, ev, event_id=1, session_id="s")
    row = read_key(c, "bash")                                    # no path token -> 'bash' key
    assert row is not None and row["kind"] == "testrun"
    assert "2 failed" in (row["value"] or "")                    # tail kept the verdict
    assert len(row["value"]) <= 500


def test_record_update_no_root_never_chain_appends(tmp_path, monkeypatch):
    """root=None (the default, and every bare unit test above) must NOT chain-append anywhere --
    not even to a MAKOTO_STATE_DIR left set by a prior test in the same process. Guards the exact
    leak this design was built to avoid."""
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path))
    c = _conn()
    record_update(
        c, {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/x.py"}},
        event_id=1, session_id="s",
    )
    from makoto import ledger as _ledger
    assert _ledger.read(root=tmp_path) == []


def test_record_update_with_root_chain_appends_touched_row(tmp_path):
    """root=<explicit> (the real _dispatch.py call site's shape) chain-appends a 'touched' row
    at that exact root, verifiable via verify_chain(root=...)."""
    from makoto import ledger as _ledger
    c = _conn()
    record_update(
        c, {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/x.py"}},
        event_id=1, session_id="s", root=tmp_path,
    )
    assert _ledger.verify_chain(root=tmp_path) is None
    rows = _ledger.read(root=tmp_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "touched"
    assert rows[0]["key"] == "src/x.py"


def test_record_update_chain_fault_never_blocks_sqlite_write(tmp_path, monkeypatch):
    """A chain-append fault must never lose the sqlite (latest-wins) write it accompanies."""
    import makoto.ledger as _ledger_mod
    def _boom(*a, **k):
        raise RuntimeError("chain unavailable")
    monkeypatch.setattr(_ledger_mod, "append", _boom)
    c = _conn()
    record_update(
        c, {"hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/x.py"}},
        event_id=1, session_id="s", root=tmp_path,
    )
    row = read_key(c, "src/x.py")
    assert row is not None
    assert row["kind"] == "touched"
