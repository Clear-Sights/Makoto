"""run_stop_checks is the L3 orchestrator's, living in _dispatch (spec §3b row 4 / §6 — Task 10).

Pins the move + the no-shim dissolution of engine.py: importing makoto.engine must fail."""
import importlib
import sqlite3


def test_run_stop_checks_lives_in_dispatch():
    from makoto._dispatch import run_stop_checks
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
              "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
              "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
    c.execute("CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
              "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")
    out = run_stop_checks(c, {"last_assistant_message": "Done. I created zzz_nope.py.",
                             "session_id": "s", "cwd": "/tmp"})
    assert any(f.pattern_id == "gate.completion" for f in out)


def test_engine_module_is_dissolved():
    try:
        importlib.import_module("makoto.engine")
    except ModuleNotFoundError:
        return
    raise AssertionError("makoto.engine must be dissolved (no shim, spec §7)")
