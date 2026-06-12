"""tests for the events-table rolling-window retention (makoto._dispatch).

The events table is a transient evidence buffer; the only production reader (_select_recent)
never looks back past a 1-hour same-session window, so anything older is dead weight. These tests
pin the hard bound: a prune runs on every ingest, old rows go, the working window stays, and the
window is env-tunable but never disables (an unbounded table is the failure mode we prevent).
"""
import sqlite3

from makoto._dispatch import (
    _event_retention_hours,
    _prune_old_events,
    _ingest_event,
    _select_recent,
)
from makoto.db import init_db


def _db(tmp_path):
    cit = tmp_path / "CITATIONS.md"
    cit.write_text("x")
    init_db(tmp_path / "state", cit)
    return sqlite3.connect(str(tmp_path / "state" / "makoto.db"), isolation_level=None)


def _insert(conn, sid, etype, hours_ago):
    """insert one event whose ts is `hours_ago` in the past."""
    conn.execute(
        "INSERT INTO events (ts, session_id, event_type, cwd, payload) "
        "VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now', ?), ?, ?, ?, ?)",
        [f"-{hours_ago} hours", sid, etype, "/tmp", '{"hook_event_name":"%s"}' % etype],
    )


def test_prune_drops_old_keeps_recent(tmp_path):
    conn = _db(tmp_path)
    _insert(conn, "s1", "PostToolUse", hours_ago=5)    # outside default 3h window
    _insert(conn, "s1", "PostToolUse", hours_ago=0.1)  # inside
    _prune_old_events(conn)
    rows = conn.execute("SELECT count(*) FROM events").fetchone()[0]
    assert rows == 1, "exactly the recent event should survive the default 3h window"


def test_window_is_env_tunable(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    _insert(conn, "s1", "PostToolUse", hours_ago=2)    # inside default 3h, OUTSIDE a 1h window
    monkeypatch.setenv("MAKOTO_EVENT_RETENTION_HOURS", "1")
    assert _event_retention_hours() == 1.0
    _prune_old_events(conn)
    assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 0


def test_nonpositive_or_garbage_window_falls_back_never_disables(tmp_path, monkeypatch):
    # a 0 / negative / unparseable value must NOT mean "keep forever" — it falls back to default.
    for bad in ("0", "-4", "", "nonsense"):
        monkeypatch.setenv("MAKOTO_EVENT_RETENTION_HOURS", bad)
        assert _event_retention_hours() == 1.5


def test_ingest_prunes_on_every_write(tmp_path):
    conn = _db(tmp_path)
    _insert(conn, "s1", "PostToolUse", hours_ago=9)    # stale
    # a fresh ingest must evict the stale row as a side effect
    _ingest_event(conn, {"session_id": "s1", "hook_event_name": "PostToolUse", "cwd": "/tmp"}, "{}")
    remaining = conn.execute("SELECT event_type, ts FROM events").fetchall()
    assert len(remaining) == 1 and remaining[0][0] == "PostToolUse"  # only the just-ingested row


def test_select_recent_window_unaffected_by_prune(tmp_path):
    # the prune window (3h) is strictly wider than the _select_recent query window (1h),
    # so a within-1h event a predicate needs is never pruned out from under it.
    conn = _db(tmp_path)
    cur = conn.execute(
        "INSERT INTO events (ts, session_id, event_type, cwd, payload) "
        "VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now','-30 minutes'), ?, ?, ?, ?)",
        ["s1", "PostToolUse", "/tmp", '{"tool_response":"https://example.com/x"}'])
    _insert(conn, "s1", "PostToolUse", hours_ago=0.01)
    now_id = conn.execute("SELECT max(id) FROM events").fetchone()[0] + 1
    _prune_old_events(conn)
    hist = _select_recent(conn, "s1", now_id)
    assert any("example.com" in str(r[4]) for r in hist), "30-min-old evidence must remain visible to predicates"


def test_ts_index_exists(tmp_path):
    conn = _db(tmp_path)
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='events'").fetchall()}
    assert "events_ts_idx" in idx, "ts-only index needed so the prune DELETE is index-assisted"
