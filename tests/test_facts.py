"""substrate/facts.py (START step 13): hook events as the facts the register lines read, with the
read ledger (path -> hash as the session saw it) and the claim reader. Each piece has a plant."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from makoto.substrate import facts as F
from makoto.substrate import line as L


def _post(tool, ti, cwd, resp=None, name="PostToolUse"):
    return {"hook_event_name": name, "tool_name": tool, "tool_input": ti, "cwd": str(cwd),
            "tool_response": resp if resp is not None else {}}


def test_a_seen_file_is_stamped_and_an_unseen_one_is_not(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    got = F.stamp(_post("Read", {"file_path": str(tmp_path / "a.py")}, tmp_path))
    assert got[F.SEEN_KEY] == {str(tmp_path / "a.py"): F.file_hash(str(tmp_path / "a.py"))}
    assert F.stamp(_post("Read", {"file_path": str(tmp_path / "gone.py")}, tmp_path)) is None
    assert F.stamp({**_post("Read", {"file_path": str(tmp_path / "a.py")}, tmp_path),
                    "hook_event_name": "PreToolUse"}) is None      # a call that may never land


def test_a_bash_read_stamps_the_files_it_names(tmp_path):
    (tmp_path / "b.md").write_text("hi\n")
    got = F.stamp(_post("Bash", {"command": "cd x; cat b.md | head -3"}, tmp_path))
    assert list(got[F.SEEN_KEY]) == ["b.md"]
    assert F.stamp(_post("Bash", {"command": "echo 'b.md is here'"}, tmp_path)) is None


def test_the_ledger_is_as_of_before_each_event_and_keyed_by_every_suffix(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text("y = 2\n")
    seen = F.stamp(_post("Read", {"file_path": str(tmp_path / "tools" / "x.py")}, tmp_path))
    fs = F.facts_of([seen, {"hook_event_name": "Stop", "last_assistant_message": "see tools/x.py",
                            "cwd": "/elsewhere"}])
    assert fs[0]["source"]["read"] == {}
    assert "tools/x.py" in fs[1]["source"]["read"] and "x.py" in fs[1]["source"]["read"]


def test_the_claim_reader_reads_kind_and_a_runner_subject_only():
    assert F.read_claim("Done: `python3 -m pytest -q` passes.") == {"kind": "clean", "subject": "python3 -m pytest -q"}
    assert F.read_claim("`START.md` passes review.") == {"kind": "clean", "subject": None}
    assert F.read_claim("It does not pass yet.") == {}
    assert F.read_claim("Should I go on?")["kind"] == "question"


def test_drift_is_a_line_over_the_ledger(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    seen = F.stamp(_post("Read", {"file_path": str(f)}, tmp_path))
    stop = {"hook_event_name": "Stop", "last_assistant_message": "a.py sets x", "cwd": str(tmp_path)}
    drift = ("event in {Pre,Stop} and exists n in refs(output) and source.read[n] and tree[n].hash "
             "and source.read[n]!=tree[n].hash")
    fs = F.facts_of([seen, stop])
    assert not L.holds(drift, fs[-1], fs[:-1])
    f.write_text("x = 2\n")                                 # changed since it was seen
    assert L.holds(drift, fs[-1], fs[:-1])


def test_the_dispatcher_stores_the_stamp(tmp_path):
    (tmp_path / "a.txt").write_text("hello\n")
    ev = _post("Read", {"file_path": str(tmp_path / "a.txt")}, tmp_path)
    ev["session_id"] = "facts"
    plugin = os.path.join(os.path.dirname(__file__), "..", "plugin")
    subprocess.run([sys.executable, "-m", "makoto.dispatch"], input=json.dumps(ev), text=True,
                   capture_output=True, cwd=plugin,
                   env={**os.environ, "MAKOTO_STATE_DIR": str(tmp_path / "state")})
    import sqlite3
    rows = sqlite3.connect(str(tmp_path / "state" / "makoto.record.db")).execute(
        "select payload from events").fetchall()
    assert any(F.SEEN_KEY in r[0] for r in rows)


def test_a_fifo_or_a_directory_is_never_read(tmp_path):
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    assert F.file_hash(str(fifo)) is None                   # would block forever if opened
    assert F.file_hash(str(tmp_path)) is None
    assert F.stamp(_post("Read", {"file_path": str(fifo)}, tmp_path)) is None
