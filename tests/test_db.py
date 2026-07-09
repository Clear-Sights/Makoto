"""tests for makoto.record.db — single init_db public API (SQLite(WAL) backend).

Covers all five tables (events, canonical_citations, config, ledger,
commitments), WAL mode, idempotency, the mtime sentinel, and config upsert.
Stdlib sqlite3 only — no importorskip (sqlite3 is always available).
"""
import sqlite3

import pytest


def _connect(db_file):
    return sqlite3.connect(str(db_file), isolation_level=None)


def test_init_db_creates_all_tables_and_wal(tmp_path):
    """init_db creates every table + sets WAL; ledger + commitments are net-new."""
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations_path = tmp_path / "CITATIONS.md"
    citations_path.write_text("Knight-Leveson 1986\n")
    init_db(state_dir, citations_path)
    db_file = state_dir / "makoto.record.db"
    assert db_file.is_file()
    conn = _connect(db_file)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"events", "canonical_citations", "config", "ledger", "commitments"} <= names
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    rows = dict(conn.execute("SELECT key, value FROM config").fetchall())
    assert "canonical_citations_path" in rows
    assert "canonical_citations_mtime" in rows
    # canonical_citations.cite is a PRIMARY KEY (duplicate insert raises)
    conn.execute("INSERT INTO canonical_citations VALUES ('Knight-Leveson 1986', 'CITATIONS.md')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO canonical_citations VALUES ('Knight-Leveson 1986', 'allowlist')")
    conn.close()


def test_init_db_is_idempotent(tmp_path):
    """second init_db on same state_dir preserves rows (CREATE TABLE IF NOT EXISTS)."""
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations_path = tmp_path / "CITATIONS.md"
    citations_path.write_text("Knight-Leveson 1986\n")
    init_db(state_dir, citations_path)
    conn = _connect(state_dir / "makoto.record.db")
    conn.execute(
        "INSERT INTO events (session_id, event_type, cwd, payload) VALUES (?, ?, ?, ?)",
        ["sess1", "PreToolUse", "/tmp", "{}"])
    conn.close()
    init_db(state_dir, citations_path)
    conn = _connect(state_dir / "makoto.record.db")
    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert n == 1  # row preserved across re-init
    conn.close()


def test_init_db_creates_state_dir_if_missing(tmp_path):
    """init_db mkdir -p's state_dir so cmd_install doesn't have to."""
    from makoto.record.db import init_db
    state_dir = tmp_path / "nonexistent" / "makoto_state"
    citations_path = tmp_path / "CITATIONS.md"
    citations_path.write_text("x")
    init_db(state_dir, citations_path)
    assert state_dir.is_dir()
    assert (state_dir / "makoto.record.db").is_file()


def test_init_db_events_insert_autoincrement_id(tmp_path):
    """post-init, INSERT INTO events gives lastrowid == 1 (the dispatcher's idiom)."""
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations_path = tmp_path / "CITATIONS.md"
    citations_path.write_text("x")
    init_db(state_dir, citations_path)
    conn = _connect(state_dir / "makoto.record.db")
    cur = conn.execute(
        "INSERT INTO events (ts, session_id, event_type, cwd, payload) "
        "VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, ?, ?)",
        ["sess1", "PreToolUse", "/tmp", '{"hook_event_name":"PreToolUse"}'])
    assert cur.lastrowid == 1
    conn.close()


def test_init_db_config_seeds_mtime_sentinel_when_path_missing(tmp_path):
    """missing citations_path -> mtime sentinel '-1'; refresh_citations treats as cache-miss."""
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    missing = tmp_path / "does_not_exist.md"
    init_db(state_dir, missing)
    conn = _connect(state_dir / "makoto.record.db")
    rows = dict(conn.execute("SELECT key, value FROM config").fetchall())
    assert rows["canonical_citations_mtime"] == "-1"
    conn.close()


def test_init_db_config_upserts_path_on_reinvoke(tmp_path):
    """re-running with a different citations_path REPLACES the seed row, no duplicates."""
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    p1 = tmp_path / "first.md"
    p1.write_text("x")
    p2 = tmp_path / "second.md"
    p2.write_text("y")
    init_db(state_dir, p1)
    init_db(state_dir, p2)
    conn = _connect(state_dir / "makoto.record.db")
    rows = dict(conn.execute("SELECT key, value FROM config").fetchall())
    assert rows["canonical_citations_path"] == str(p2)
    assert len(rows) == 2  # exactly the two known keys
    conn.close()
