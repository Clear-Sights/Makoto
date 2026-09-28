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
    got = F.stamp(_post("Bash", {"command": "cat b.md | head -3"}, tmp_path))
    assert list(got[F.SEEN_KEY]) == [str(tmp_path / "b.md")]
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
    assert F.file_hash(str(tmp_path)) is None               # every platform has directories
    if not hasattr(os, "mkfifo"):                           # Windows: no FIFOs to open
        return
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    assert F.file_hash(str(fifo)) is None                   # would block forever if opened
    assert F.file_hash(str(tmp_path)) is None
    assert F.stamp(_post("Read", {"file_path": str(fifo)}, tmp_path)) is None



# ---- a Codex gpt-6-astra read of 6e04caf..149d148: eight witnessed defects, each kept here ----

def test_a_file_swapped_for_a_fifo_after_the_stat_cannot_hang(tmp_path, monkeypatch):
    import signal
    if not (hasattr(os, "mkfifo") and hasattr(signal, "SIGALRM")):   # Windows: no FIFO to swap in
        assert F.file_hash(str(tmp_path)) is None
        return
    p = tmp_path / "x"
    p.write_text("ok")
    real = os.stat

    def swap(path, *a, **k):                    # the name changes between a stat and an open
        st = real(path, *a, **k)
        if str(path) == str(p) and not os.path.exists(str(p) + ".done"):
            os.unlink(p)
            os.mkfifo(p)
            open(str(p) + ".done", "w").close()
        return st
    monkeypatch.setattr(F.os, "stat", swap)

    class Blocked(BaseException):             # not an OSError, so no handler can swallow it
        pass

    def boom(*_):
        raise Blocked("file_hash blocked on a FIFO")
    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(3)
    try:
        got = F.file_hash(str(p))               # it must return, whatever it returns
        assert got is None or len(got) == 16
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_a_nul_in_a_path_is_no_hash_and_the_event_is_still_stored(tmp_path):
    assert F.file_hash("bad\x00path") is None
    ev = _post("Read", {"file_path": "bad\x00path"}, tmp_path)
    ev["session_id"] = "nul"
    plugin = os.path.join(os.path.dirname(__file__), "..", "plugin")
    subprocess.run([sys.executable, "-m", "makoto.dispatch"], input=json.dumps(ev), text=True,
                   capture_output=True, cwd=plugin, env={**os.environ, "MAKOTO_STATE_DIR": str(tmp_path / "st")})
    assert (tmp_path / "st" / "makoto.record.db").exists()


def test_a_cd_in_the_command_is_followed(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.py").write_text("UNSEEN")
    (tmp_path / "sub" / "a.py").write_text("SEEN")
    got = F.stamp(_post("Bash", {"command": "cd sub; cat a.py"}, tmp_path))
    assert list(got[F.SEEN_KEY]) == [str(tmp_path / "sub" / "a.py")]


def test_a_background_launch_is_not_stamped(tmp_path):
    (tmp_path / "a.py").write_text("old")
    assert F.stamp(_post("Bash", {"command": "sleep 60; cat a.py", "run_in_background": True}, tmp_path)) is None


def test_a_suffix_that_names_another_file_here_is_not_seen(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.py").write_text("seen")
    (tmp_path / "b" / "x.py").write_text("unseen")
    seen = F.stamp(_post("Read", {"file_path": str(tmp_path / "a" / "x.py")}, tmp_path))
    fs = F.facts_of([seen, {"hook_event_name": "Stop", "cwd": str(tmp_path / "b"), "last_assistant_message": "See x.py"}])
    assert "x.py" not in fs[-1]["source"]["read"]
    fs = F.facts_of([seen, {"hook_event_name": "Stop", "cwd": str(tmp_path), "last_assistant_message": "See a/x.py"}])
    assert "a/x.py" in fs[-1]["source"]["read"]


def test_an_extensionless_file_argument_is_stamped(tmp_path):
    (tmp_path / "README").write_text("seen")
    got = F.stamp(_post("Bash", {"command": "cat README"}, tmp_path))
    assert list(got[F.SEEN_KEY]) == [str(tmp_path / "README")]


def test_quotes_and_questions_are_not_clean_claims():
    assert F.read_claim('"All tests passed."') == {}
    assert F.read_claim("Do `pytest` tests pass?")["kind"] == "question"


def test_the_subject_comes_from_the_claim_sentence():
    assert F.read_claim("`pytest` failed. `npm test` passed.") == {"kind": "clean", "subject": "npm test"}


def test_cd_follows_the_shell(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.py").write_text("ROOT")
    (tmp_path / "sub" / "a.py").write_text("SUB")
    seen = lambda cmd: sorted(F.stamp(_post("Bash", {"command": cmd}, tmp_path))[F.SEEN_KEY])
    assert seen("(cd sub); cat a.py") == [str(tmp_path / "a.py")]           # a subshell's cd ends
    assert seen("echo ready\ncd sub\ncat a.py") == [str(tmp_path / "sub" / "a.py")]
    assert seen("cd -- sub; cat a.py") == [str(tmp_path / "sub" / "a.py")]


def test_a_fenced_example_is_not_a_claim():
    assert F.read_claim("```text\nAll tests passed.\n```") == {}


def test_a_second_subshell_starts_from_the_parents_directory(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.py").write_text("ROOT")
    (tmp_path / "sub" / "a.py").write_text("SUB")
    got = F.stamp(_post("Bash", {"command": "(cd sub); (cat a.py)"}, tmp_path))
    assert sorted(got[F.SEEN_KEY]) == [str(tmp_path / "a.py")]
