"""R's own math: plants (an object never observed stays unobserved) and look-alikes (read,
written or created objects are observed), plus the three field false alarms from the Makoto
audit, each rebuilt as a look-alike from its description."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugin", "makoto2"))
from observed import Obs, Record, record

CWD = "/repo"


def test_slash_words_need_path_evidence(tmp_path):
    from observed import _text_objects

    prose = 'add/subtract and/or read/write'
    assert not _text_objects(prose, str(tmp_path))
    assert not _text_objects('Choose add/subtract.', str(tmp_path))
    (tmp_path / 'add').mkdir()
    path = tmp_path / 'add' / 'subtract'
    path.write_text('source')
    assert _text_objects(prose, str(tmp_path)) == {str(path)}
    path.unlink()
    assert not _text_objects(prose, str(tmp_path))
    for spelling in ('add/subtract.txt', './add/subtract', '../add/subtract',
                     '/add/subtract', '~/add/subtract'):
        assert _text_objects(spelling, str(tmp_path))


def post(tool, ti, tr=None, failure=False, **extra):
    ev = {"hook_event_name": "PostToolUseFailure" if failure else "PostToolUse",
          "tool_name": tool, "tool_input": ti, "tool_response": tr, "cwd": CWD}
    ev.update(extra)
    return ev


def pre(tool, ti):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti, "cwd": CWD}


def bash(cmd, stdout="", failure=False, **tr):
    return post("Bash", {"command": cmd}, dict({"stdout": stdout, "stderr": ""}, **tr),
                failure=failure)


def seen(history, act):
    rec = record(history)
    return rec.observed(rec.objects_of(act))


# ---- the interface ------------------------------------------------------------------------------

def test_interface_shape():
    rec = record([bash("cat a.txt", "x"), pre("Bash", {"command": "rm a.txt"})])
    assert isinstance(rec, Record) and len(rec.obs) == 1, "only settled events become Obs"
    o = rec.obs[0]
    assert isinstance(o, Obs)
    assert Obs._fields == ("seq", "tool", "input", "output", "exit", "failed", "objects",
                           "written", "created", "send", "search")
    assert o.seq == 0 and o.tool == "Bash" and o.output == "x" and o.failed is False
    assert "/repo/a.txt" in o.objects and o.written == frozenset()


def test_deterministic():
    h = [bash("mkdir F2 && printf 'passed 8/8' >> OUT.tsv", "ok"), post("Read", {"file_path": "b.py"})]
    assert record(h).obs == record(h).obs


# ---- plants: an object never observed is not observed ------------------------------------------

def test_plant_unobserved_object_blocks():
    # discriminant: history names a different object (a.txt) than the act (src)
    assert not seen([bash("cat a.txt", "hello")], pre("Bash", {"command": "rm -rf src"}))


def test_plant_empty_history():
    # discriminant: no settled event at all
    assert not seen([], pre("Bash", {"command": "rm -rf F2"}))


def test_plant_unsettled_event_observes_nothing():
    # discriminant: the only event naming the object is a PreToolUse, never settled
    assert not seen([pre("Read", {"file_path": "/repo/src/a.py"})],
                    pre("Bash", {"command": "rm src/a.py"}))


def test_plant_denied_call_did_not_execute():
    # discriminant: the event naming F2 settled as a hook denial, so no result came back
    denied = post("Bash", {"command": "mkdir F2"},
                  None, failure=True, error="PreToolUse:Bash hook error: makoto: row x denied")
    assert not seen([denied], pre("Bash", {"command": "rm -rf F2"}))


def test_plant_parent_directory_does_not_observe_child():
    # discriminant: only the parent directory src/ was named, never src/writer.py
    assert not seen([bash("ls -la src/", "total 0")], pre("Edit", {"file_path": "src/writer.py"}))


def test_plant_before_bound():
    # discriminant: the observing event sits at seq 1, the bound excludes it then admits it
    h = [bash("true"), post("Read", {"file_path": "a.py"}, {"file": {"content": ""}})]
    rec = record(h)
    assert not rec.observed({"/repo/a.py"}, before=1)
    assert rec.observed({"/repo/a.py"}, before=2)


def test_plant_verdict_with_no_earlier_run():
    # discriminant: no earlier output printed 8/8
    assert not seen([bash("ls")], pre("Bash", {"command": "printf 'passed 8/8\\n' >> OUTCOMES.tsv"}))


def test_plant_program_name_is_not_an_object_of_observation():
    # discriminant: a runner ran, but nothing it named or printed is build/
    assert not seen([bash("python3 -m pytest -q", "58 passed in 2.0s")],
                    pre("Bash", {"command": "rm -rf build/"}))


def test_plant_code_call_is_not_a_file():
    # discriminant: json.load is followed by "(": a call, not name.ext
    rec = record([bash("python3 -c 'import json; json.load(x)'")])
    assert "/repo/json.load" not in rec.obs[0].objects


# ---- look-alikes: read, written, created objects are observed ----------------------------------

def test_read_object_is_observed():
    # discriminant: a Read of the exact file the act removes
    assert seen([post("Read", {"file_path": "/repo/src/a.py"}, {"file": {"content": "x"}})],
                pre("Bash", {"command": "rm src/a.py"}))


def test_written_object_is_observed():
    # discriminant: a Write of a new file (type create)
    rec = record([post("Write", {"file_path": "notes.md", "content": "x"}, {"type": "create"})])
    assert rec.obs[0].written == {"/repo/notes.md"} and rec.obs[0].created == {"/repo/notes.md"}
    assert rec.observed({"/repo/notes.md"})


def test_edit_writes_but_does_not_create():
    # discriminant: an Edit of an existing file (type update)
    rec = record([post("Edit", {"file_path": "a.py", "old_string": "x", "new_string": "y"},
                       {"type": "update"})])
    assert rec.obs[0].written == {"/repo/a.py"} and rec.obs[0].created == frozenset()


def test_output_naming_an_object_observes_it():
    # discriminant: the object appears only in the output, not the input
    assert seen([bash("git status --short", " M src/reader.py")],
                pre("Edit", {"file_path": "src/reader.py"}))


def test_red_run_still_executed():
    # discriminant: a failure with a known exit code is a result that came back
    h = [bash("cat src/a.py", "", failure=True, exitCode=1)]
    assert seen(h, pre("Bash", {"command": "rm src/a.py"}))


def test_redirect_writes_and_creates_new_file():
    # discriminant: a clobbering redirect to a path no earlier event named
    o = record([bash("echo hi > out/new.txt")]).obs[0]
    assert o.written == {"/repo/out/new.txt"} and o.created == {"/repo/out/new.txt"}


def test_search_fields():
    # discriminant: a grep and a Glob that both came back empty
    o = record([bash("grep -rn needle src", "")]).obs[0]
    assert o.search == ("/repo/src", "needle", True)
    g = record([post("Glob", {"pattern": "**/*.py"}, {"filenames": [], "numFiles": 0})]).obs[0]
    assert g.search == ("/repo", "**/*.py", True)


def test_send_text():
    # discriminant: a reply tool carries text; a Bash call sends nothing
    o = record([post("mcp__hearthbot__reply", {"text": "done"}, {})]).obs[0]
    assert o.send == "done"
    assert record([bash("echo x")]).obs[0].send == ""


# ---- field false alarms (Makoto audit, this session) -> observed -------------------------------

SNIPPET = ("python3 - <<'EOF'\n"
           "import json,glob\n"
           "for f in sorted(glob.glob('out/*.json')):\n"
           "    d = json.load(open('out/results.json'))\n"
           "    print(f, d['n'])\n"
           "EOF")


def test_field_pasted_fix_read_only_snippets_change_no_file_and_count_as_observation():
    """gate.pasted_fix at Stop: two read-only heredoc snippets reading the same output file were
    read as one repair landing at a second site. Neither wrote anything, and the later one
    observes the object the earlier one named."""
    # discriminant: heredoc fed to python reads out/results.json, writes nothing
    h = [bash(SNIPPET, "out/results.json 8"), bash(SNIPPET, "out/results.json 8")]
    rec = record(h)
    assert all(o.written == frozenset() and o.created == frozenset() for o in rec.obs)
    assert "/repo/out/results.json" in rec.obs[1].objects
    assert rec.observed({"/repo/out/results.json"}, before=1)
    assert rec.observed(rec.objects_of(h[1]), before=1)


def test_field_report_before_run_printf_after_run_printed_the_results():
    """gate.report_before_run: `printf ... >> OUTCOMES.tsv` writing "passed 8/8" after an earlier
    settled run had printed those results."""
    # discriminant: the earlier run's output printed the same 8/8 the printf writes
    h = [bash("sh field/run.sh", "case a ok\n...\npassed 8/8\n")]
    act = pre("Bash", {"command": "printf 'F2\\tpassed 8/8\\n' >> OUTCOMES.tsv"})
    rec = record(h)
    assert "8/8" in rec.objects_of(act)
    assert rec.observed(rec.objects_of(act))


def test_field_report_before_run_heredoc_fixture_quoting_verdicts():
    """Heredoc-written test fixtures quoting verdict phrases as data, after the run whose
    phrases they quote."""
    # discriminant: the fixture's quoted counts are exactly what the earlier run printed
    h = [bash("python3 field/score.py", "12 passed, 1 failed in 0.4s")]
    act = pre("Bash", {"command": "cat > tests/fixtures/verdicts.txt <<'EOF'\n"
                                  "12 passed, 1 failed in 0.4s\nEOF"})
    rec = record(h)
    assert rec.observed(rec.objects_of(act))


def test_field_unobserved_destruction_rm_of_dirs_created_by_mkdir():
    """gate.unobserved_destruction: `rm -rf F2 F4` of directories an earlier settled command
    created with mkdir."""
    # discriminant: F2 and F4 are in the earlier event's created set
    h = [bash("mkdir -p F2 F4 && cp seed.txt F2/", "")]
    rec = record(h)
    assert {"/repo/F2", "/repo/F4"} <= rec.obs[0].created
    act = pre("Bash", {"command": "rm -rf F2 F4"})
    assert rec.observed(rec.objects_of(act))


def test_field_destruction_plant_neighbour_still_blocks():
    """The same session shape, but the removed directory was never created or named."""
    # discriminant: F3 was never created or named
    rec = record([bash("mkdir -p F2 F4", "")])
    assert not rec.observed(rec.objects_of(pre("Bash", {"command": "rm -rf F3"})))


# ---- turns and user texts -----------------------------------------------------------------------

def test_turn_start_is_first_obs_after_last_boundary():
    # discriminant: two boundaries; only the later (a Stop) counts
    h = [{"hook_event_name": "UserPromptSubmit", "prompt": "fix it"}, bash("cat a.txt"),
         {"hook_event_name": "Stop"}, bash("cat b.txt"), bash("cat c.txt")]
    rec = record(h)
    assert rec.turn_start == 3 and len(rec.obs) == 3
    assert rec.user_texts == ["fix it"]


def test_turn_start_zero_without_boundary():
    # discriminant: no Stop or UserPromptSubmit in the history
    assert record([bash("cat a.txt")]).turn_start == 0


def test_user_texts_from_fetched_thread_user_entries_only():
    # discriminant: one user entry and one agent entry in the fetched thread
    import json
    fetched = post("mcp__hearthbot__fetch_thread", {"thread_id": "cmsg_1"},
                   json.dumps({"messages": [{"author": "user", "body": "use the seed"},
                                            {"author": "agent", "body": "ok"}]}))
    rec = record([{"hook_event_name": "UserPromptSubmit", "prompt": "go"}, fetched])
    assert rec.user_texts == ["go", "use the seed"]
    assert rec.turn_start == 1
