"""A1.3 teeth: run_stop_checks must thread the events-table `history` into the GateContext it builds,
so the fabrication gates can walk it. Drop the `history=` thread -> this reddens."""
import sqlite3

import makoto._dispatch as D


def _conn():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
              "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
              "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
    c.execute("CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
              "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")
    return c


def test_run_stop_checks_threads_history_into_context(monkeypatch):
    captured = {}
    real = D.GateContext

    def spy(**kw):
        captured.update(kw)
        return real(**kw)

    monkeypatch.setattr(D, "GateContext", spy)
    hist = [(1, "t", "live.posttooluse", "/repo",
             '{"tool_name":"Bash","tool_input":{"command":"ls"},"tool_response":{"stdout":"x"}}')]
    D.run_stop_checks(_conn(), {"last_assistant_message": "hi", "session_id": "s", "cwd": "/repo"}, hist)
    assert captured.get("history") == hist
