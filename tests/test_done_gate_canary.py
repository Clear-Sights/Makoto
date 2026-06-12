"""End-to-end contamination-canary test for the completion ('done'/plan-done) Stop gate.

The done gate must BLOCK a "produced X" claim when X is neither in the results ledger nor on disk,
and stay SILENT when X actually exists on disk — planted-incorrect fires, planted-correct passes.
Neither end may collapse: a fire-always mutant reds the silent case, a fire-never mutant reds the
block case. Exercises the live run_stop_checks path the dispatcher invokes on every Stop, resolving
the cited file against payload['cwd'] (not the process cwd).
"""
import sqlite3

from makoto._dispatch import run_stop_checks


def _conn():
    """in-memory DB with the two tables run_stop_checks reads (commitments + ledger), matching the
    live schema. Empty ledger => the only grounding for a 'produced' claim is the filesystem."""
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
              "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
              "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
    c.execute("CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
              "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")
    return c


def _claim(c, text, cwd):
    return run_stop_checks(c, {"last_assistant_message": text, "session_id": "s", "cwd": str(cwd)})


def test_done_gate_blocks_claim_of_absent_file(tmp_path):
    # tmp_path is empty -> the cited file does not exist and is not in the ledger
    findings = _claim(c := _conn(), "Done — I created `plan_step_absent_q7x.py`. All steps complete.", tmp_path)
    assert any(f.pattern_id == "gate.completion" for f in findings), \
        "a done-claim citing an absent, unrecorded file must block"


def test_done_gate_silent_when_file_really_exists(tmp_path):
    (tmp_path / "plan_step_real_q7x.py").write_text("print('real')\n")   # exists + non-empty
    findings = _claim(_conn(), "Done — I created `plan_step_real_q7x.py`. All steps complete.", tmp_path)
    assert not any(f.pattern_id == "gate.completion" for f in findings), \
        "a done-claim citing a file that truly exists must NOT false-block"


def test_done_gate_canary_neither_end_collapses(tmp_path):
    """Same phrasing, two worlds, one test: absent fires and present stays silent, so neither a
    fire-always nor a fire-never mutant survives."""
    (tmp_path / "present_x9.py").write_text("x = 1\n")
    fire = _claim(c := _conn(), "I created `missing_x9.py`.", tmp_path)
    silent = _claim(c, "I created `present_x9.py`.", tmp_path)
    assert any(f.pattern_id == "gate.completion" for f in fire)
    assert not any(f.pattern_id == "gate.completion" for f in silent)
