"""§7.1 content-depth: a zero-byte Write does not discharge a production claim.

The completion (and advance) gate's discharge was existence-deep — a zero-byte Write of X
discharged "I implemented X". makoto now records Write-emptiness in the ledger so the gate
is content-deep: an empty Write of a non-conventional file does not satisfy a production
claim. Unknown/edited/conventional-empty cases fail open (never a false block).
"""
import os
import sqlite3

from makoto.checks._shared import _discharged
from makoto.checks.claimedProduceAbsent import completion_gate
from makoto._dispatch import run_stop_checks
from makoto import ledger as L


def _conn():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
              "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)")
    c.execute("CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
              "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
              "retract_param TEXT, created_event_id INTEGER, ts TEXT)")
    return c


# --- ledger records Write emptiness (kind stays 'touched'; value = stripped length) ---

def test_empty_write_records_zero_length():
    c = _conn()
    L.record_update(c, {"tool_name": "Write", "tool_input": {"file_path": "auth.py", "content": ""}},
                    event_id=1, session_id="s")
    row = L.read_key(c, "auth.py")
    assert row["kind"] == "touched" and row["value"] == "0"

def test_whitespace_only_write_is_empty():
    c = _conn()
    L.record_update(c, {"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "  \n\t\n"}},
                    event_id=1, session_id="s")
    assert L.read_key(c, "a.py")["value"] == "0"

def test_nonempty_write_records_positive_length():
    c = _conn()
    L.record_update(c, {"tool_name": "Write", "tool_input": {"file_path": "auth.py", "content": "x = 1\n"}},
                    event_id=1, session_id="s")
    row = L.read_key(c, "auth.py")
    assert row["kind"] == "touched" and int(row["value"]) > 0

def test_edit_records_none_value_not_zero():
    # an Edit patches existing content — it is NOT a zero-byte production; never an empty key.
    c = _conn()
    L.record_update(c, {"tool_name": "Edit", "tool_input": {"file_path": "auth.py", "new_string": "y"}},
                    event_id=1, session_id="s")
    row = L.read_key(c, "auth.py")
    assert row["kind"] == "touched" and row["value"] is None


# --- _discharged content-depth ---

def test_discharged_empty_write_does_not_discharge():
    assert _discharged("auth.py", {"auth.py"}, None, empty_keys={"auth.py"}) is False

def test_discharged_nonempty_write_discharges():
    assert _discharged("auth.py", {"auth.py"}, None, empty_keys=set()) is True

def test_discharged_conventional_empty_discharges():
    assert _discharged("pkg/__init__.py", {"pkg/__init__.py"}, None, empty_keys={"pkg/__init__.py"}) is True

def test_discharged_backcompat_no_empty_keys_is_old_behavior():
    assert _discharged("auth.py", {"auth.py"}, None) is True

def test_discharged_disk_empty_no_ledger_fails():
    assert _discharged("auth.py", set(), lambda p: True, fs_size=lambda p: 0) is False

def test_discharged_disk_nonempty_no_ledger_discharges():
    assert _discharged("auth.py", set(), lambda p: True, fs_size=lambda p: 12) is True

def test_discharged_empty_ledger_but_disk_nonempty_discharges():
    # ledger recorded an empty Write, but the file now carries content (e.g. later filled) -> discharged
    assert _discharged("auth.py", {"auth.py"}, lambda p: True,
                         empty_keys={"auth.py"}, fs_size=lambda p: 30) is True


# --- completion_gate end-to-end ---

def test_completion_gate_fires_on_empty_production():
    f = completion_gate("I implemented `auth.py`.", touched_keys={"auth.py"}, empty_keys={"auth.py"})
    assert f is not None and f.pattern_id == "gate.completion"

def test_completion_gate_silent_on_real_production():
    f = completion_gate("I implemented `auth.py`.", touched_keys={"auth.py"}, empty_keys=set())
    assert f is None


# --- run_stop_checks wiring: an empty Write recorded, then a production claim, fires ---

def test_run_stop_checks_flags_empty_write_production():
    c = _conn()
    L.record_update(c, {"tool_name": "Write", "tool_input": {"file_path": "auth.py", "content": ""}},
                    event_id=1, session_id="s")
    out = run_stop_checks(c, {"last_assistant_message": "I implemented `auth.py`.",
                               "session_id": "s", "cwd": "/nonexistent-cwd-xyz"})
    assert any(getattr(f, "pattern_id", "") == "gate.completion" for f in out)

def test_run_stop_checks_silent_on_nonempty_write_production():
    c = _conn()
    L.record_update(c, {"tool_name": "Write", "tool_input": {"file_path": "auth.py", "content": "real\n"}},
                    event_id=1, session_id="s")
    out = run_stop_checks(c, {"last_assistant_message": "I implemented `auth.py`.",
                               "session_id": "s", "cwd": "/nonexistent-cwd-xyz"})
    assert not any(getattr(f, "pattern_id", "") == "gate.completion" for f in out)


# --- run_stop_checks resolves the filesystem against payload['cwd'], not the process cwd ---
# These pin the cwd-sourcing + fs closures (_dispatch.py). They deliberately use NO
# ledger signal so discharge falls through to the live filesystem under the recorded cwd.

def test_run_stop_checks_resolves_existing_file_against_payload_cwd(tmp_path):
    # _dispatch.py `payload.get("cwd") or os.getcwd()` + `return os.path.exists(...)`:
    # a production claim for a non-empty file that exists under payload["cwd"] is discharged ->
    # gate SILENT. The L559 `and` mutant (resolves against os.getcwd()) and the L586 `return
    # None` mutant both fail to find the file there and falsely fire. The unique filename cannot
    # collide with the test-runner's actual cwd, so the witness is deterministic.
    c = _conn()
    (tmp_path / "ledgerless_unique_x7q.py").write_text("def f():\n    return 1\n")
    out = run_stop_checks(c, {"last_assistant_message": "I implemented `ledgerless_unique_x7q.py`.",
                               "session_id": "s", "cwd": str(tmp_path)})
    assert not any(getattr(f, "pattern_id", "") == "gate.completion" for f in out)


def test_run_stop_checks_fires_on_empty_file_under_payload_cwd(tmp_path):
    # _dispatch.py `getsize(full) if isfile(full) else None`: a production claim for a file that
    # EXISTS but is empty (size 0) under payload["cwd"] is NOT discharged -> gate FIRES. The
    # `return None` mutant erases the size signal, fails open to discharged, and wrongly stays
    # silent on an empty-production claim (the §7.1 content-depth break this whole module guards).
    c = _conn()
    (tmp_path / "empty_unique_x7q.py").write_text("")
    out = run_stop_checks(c, {"last_assistant_message": "I implemented `empty_unique_x7q.py`.",
                               "session_id": "s", "cwd": str(tmp_path)})
    assert any(getattr(f, "pattern_id", "") == "gate.completion" for f in out)


def test_run_stop_checks_empty_text_returns_empty_list_not_none():
    # _dispatch.py `if not text: return []`: an empty last_assistant_message must return an EMPTY
    # LIST, not None. The _dispatch call site iterates the result directly in a list
    # comprehension (`[... for f in run_stop_checks(...)]`), so the `return None` mutant would
    # raise TypeError and crash the hook on any text-less Stop event. A normal-path early return,
    # not an except branch — it has to be pinned, not documented.
    c = _conn()
    out = run_stop_checks(c, {"last_assistant_message": "", "session_id": "s", "cwd": "/x"})
    assert out == []
