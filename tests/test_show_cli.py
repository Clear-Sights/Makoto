"""tests for `makoto show <key>` — read-only ledger inspection (never fires)."""
import sqlite3

from makoto.record import ledger
from makoto import __main__ as cli
from makoto.record.db import init_db


def _state_with_ledger(tmp_path):
    state_dir = tmp_path / "makoto_state"
    state_dir.mkdir(parents=True)
    cit = tmp_path / "CITATIONS.md"
    cit.write_text("x")
    init_db(state_dir, cit)
    return state_dir


def test_show_reads_ledger_row(tmp_path, monkeypatch, capsys):
    state_dir = _state_with_ledger(tmp_path)
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"), isolation_level=None)
    ledger.record_update(
        conn,
        {"hook_event_name": "PostToolUse", "tool_name": "Write",
         "tool_input": {"file_path": "src/auth.py"}},
        event_id=5, session_id="s")
    conn.close()
    monkeypatch.setattr("makoto.record.state._state_dir", lambda: state_dir)
    rc = cli._cmd_show("src/auth.py")
    assert rc == 0
    out = capsys.readouterr().out
    assert "touched" in out


def test_show_no_record(tmp_path, monkeypatch, capsys):
    state_dir = _state_with_ledger(tmp_path)
    monkeypatch.setattr("makoto.record.state._state_dir", lambda: state_dir)
    rc = cli._cmd_show("never/touched.py")
    assert rc == 0
    assert "no record" in capsys.readouterr().out


def test_show_no_db_is_failsoft(tmp_path, monkeypatch, capsys):
    state_dir = tmp_path / "makoto_state"  # not created — no makoto.record.db
    monkeypatch.setattr("makoto.record.state._state_dir", lambda: state_dir)
    rc = cli._cmd_show("anything.py")
    assert rc == 0  # fail-soft: a friendly note, never a crash
