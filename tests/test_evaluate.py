"""A plant (must block, with its row) and a look-alike (the same act done right, silent) per row."""
import importlib.util
import json
import os
from typing import NamedTuple, Optional

import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.join(TESTS, "..", "plugin", "makoto2")
_spec = importlib.util.spec_from_file_location("evaluate", os.path.join(HERE, "evaluate.py"))
V = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V)


class Obs(NamedTuple):
    seq: int
    tool: str
    input: dict
    output: str = ""
    exit: Optional[int] = 0
    failed: bool = False
    objects: frozenset = frozenset()
    written: frozenset = frozenset()
    created: frozenset = frozenset()
    send: str = ""
    search: Optional[tuple] = None


class Record:
    def __init__(self, obs, turn_start=None, user_texts=()):
        self.obs = list(obs)
        self.turn_start = turn_start
        self.user_texts = list(user_texts)

    def observed(self, objects, before=None):
        objs = set(objects)
        return any((before is None or o.seq < before) and not o.failed
                   and objs & (o.objects | o.written | o.created) for o in self.obs)

    def objects_of(self, event):
        return frozenset()


WORDS = os.path.join(TESTS, "_test_words.tsv")
CFG = V.load_cfg(os.path.join(HERE, "config.json"))


@pytest.fixture(scope="module")
def rows():
    with open(WORDS, "w", encoding="utf-8") as fh:
        fh.write("id\ttime\twhere\ttext\nc1\tt\ttimeline\tthe mesh is the chart\n")
    rs = V.load_rows(os.path.join(HERE, "rows.tsv"), CFG)
    for r in rs:
        if "words" in r["args"]:
            r["args"]["words"] = WORDS
    yield rs
    os.remove(WORDS)


REPLY = "mcp__hearthbot__reply"
START = "mcp__hearthbot__start_thread_session"
NOTE = "mcp__hearthbot__message_thread"
FETCH = "mcp__hearthbot__fetch_thread"


def pre(tool, **ti):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti}


def reply(text):
    return pre(REPLY, text=text)


READ_X = Obs(1, "Read", {"file_path": "/r/a.py"}, "x = 1", objects=frozenset({"/r/a.py"}))

CASES = [
    # id, record, event (plant), record, event (look-alike)
    ("R01", Record([]), reply("Done with step 2. Should I merge it?"),
     Record([]), reply("Done with step 2; merging it next as the default.")),
    ("R01", Record([]), {"hook_event_name": "Stop", "last_assistant_message": "Want me to push this?"},
     Record([]), {"hook_event_name": "Stop", "last_assistant_message": "Pushing next; that is the default."}),
    ("R03", Record([Obs(5, START, {"prompt": "a"}, "started")], turn_start=4), pre(START, prompt="b"),
     Record([Obs(2, START, {"prompt": "a"}, "started")], turn_start=4), pre(START, prompt="b")),
    ("R04", Record([Obs(1, NOTE, {"session_id": "s1", "message": "a"}, "sent")]),
     pre(NOTE, session_id="s1", message="b"),
     Record([Obs(1, NOTE, {"session_id": "s1", "message": "a"}, "sent"),
             Obs(2, FETCH, {"thread_id": "t"}, '{"session_id": "s1", "body": "done"}')]),
     pre(NOTE, session_id="s1", message="b")),
    ("R05", Record([]), reply("Codex is not installed on this box."),
     Record([Obs(1, "Bash", {"command": "which codex"}, "", search=("PATH", "codex", True))]),
     reply("Codex is not installed on this box.")),
    ("R06", Record([Obs(1, FETCH, {"thread_id": "t"}, "harm went to 37 cases")]), reply("Harm is down to 37 cases."),
     Record([Obs(1, FETCH, {"thread_id": "t"}, "harm went to 37 cases")]),
     reply("The DetIO thread reports harm down to 37 cases.")),
    ("R07", Record([]), reply('His words: "ship it tonight"'),
     Record([]), reply('His words: "the mesh is the chart"')),
    ("R08", Record([Obs(1, "Glob", {"pattern": "/r/*.py"}, "/r/a.py\n/r/b.py")]), pre("Write", file_path="/r/plan.md", content="Edit /r/a.py and /r/b.py"),
     Record([READ_X]), pre("Write", file_path="/r/plan.md", content="Edit /r/a.py and /r/b.py")),
    ("R09", Record([Obs(1, "Bash", {"command": "rm -rf x"}, "PreToolUse hook denied this", exit=None, failed=True)]),
     pre("Bash", command="rm -rf x"),
     Record([Obs(1, "Bash", {"command": "rm -rf x"}, "PreToolUse hook denied this", exit=None, failed=True),
             Obs(2, "Read", {"file_path": "/r/x"}, "ok", objects=frozenset({"/r/x"}))]),
     pre("Bash", command="rm -rf x")),
    ("R10", Record([]), pre("Bash", command="for i in $(seq 1 30); do curl -s u && break; sleep 10; done"),
     Record([]), pre("Bash", command="for i in $(seq 1 30); do curl -s u && break; sleep 10; done", timeout=600000)),
    ("R11", Record([]), reply("PR #12 merged and CI passed."),
     Record([Obs(1, "Bash", {"command": "gh pr view 12"}, "state: MERGED\nchecks: all passed")]),
     reply("PR #12 merged and CI passed.")),
    ("R12", Record([]), reply("There are 14 rows in docs/MAP.tsv now."),
     Record([Obs(1, "Read", {"file_path": "/r/docs/MAP.tsv"}, "..", objects=frozenset({"/r/docs/MAP.tsv"}))]),
     reply("There are 14 rows in docs/MAP.tsv now.")),
    ("R13", Record([Obs(1, "Bash", {"command": "ls /r"}, "a b")]), pre("Bash", command="ls /r"),
     Record([Obs(1, "Bash", {"command": "ls /r"}, "a b"),
             Obs(2, "Write", {"file_path": "/r/c"}, "", written=frozenset({"/r/c"}))]),
     pre("Bash", command="ls /r")),
]


@pytest.mark.parametrize("rid,prec,pev,lrec,lev", CASES, ids=[c[0] for c in CASES])
def test_plant_blocks_and_lookalike_silent(rows, rid, prec, pev, lrec, lev):
    out = V.evaluate(rows, prec, pev)
    assert out is not None and out["row"] == rid, out
    assert rid in out["message"] and "source:" in out["message"] and out["objects"]
    assert V.evaluate(rows, lrec, lev) is None


def test_every_row_has_a_case_and_a_verbatim_source(rows):
    assert {r["id"] for r in rows} == {c[0] for c in CASES}
    mem = open("/tmp/claude/memory/team/silo/MEMORY.md", encoding="utf-8").read()
    words = open("/mnt/project-files/VERIFY/WORDS.tsv", encoding="utf-8").read()
    for r in rows:
        quoted = r["source"].split(': "', 1)[1].rsplit('"', 1)[0]
        assert quoted in mem or quoted in words, r["id"]


def test_config_keys_cover_config():
    keys = {ln.split("\t")[0] for ln in open(os.path.join(HERE, "CONFIG_KEYS.txt")) if ln.strip()}
    assert keys == set(json.load(open(os.path.join(HERE, "config.json"))))
