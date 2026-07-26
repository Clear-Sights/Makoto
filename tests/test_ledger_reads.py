"""ledger.py owns the read helpers touched_keys / empty_write_keys / latest_testrun (spec §3b)."""
import sqlite3


def _conn():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
              "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")
    return c


def test_ledger_read_helpers_exist_and_read():
    from makoto.record import ledger as L
    assert hasattr(L, "touched_keys") and hasattr(L, "empty_write_keys") and hasattr(L, "latest_testrun")
    c = _conn()
    c.execute("INSERT INTO ledger VALUES ('a.py','5','touched',NULL,1,'s','t1')")
    c.execute("INSERT INTO ledger VALUES ('b.py','0','touched',NULL,2,'s','t2')")
    c.execute("INSERT INTO ledger VALUES ('run','=== 1 failed ===','testrun',1,3,'s','t3')")
    # touched_keys is DELIBERATELY broad — ALL session keys regardless of kind (the gate's
    # fail-open design: any ledger trace of a location discharges a produce-claim, so neither a
    # false positive nor a false negative). So 'run' (a testrun key) is included — do NOT narrow
    # this to kind='touched' (that would shrink the fail-open net). empty_write_keys IS kind-scoped.
    assert L.touched_keys(c, "s") == {"a.py", "b.py", "run"}
    assert L.empty_write_keys(c, "s") == {"b.py"}
    assert L.latest_testrun(c, "s") == "=== 1 failed ==="
