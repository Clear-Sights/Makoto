"""A plant (must block, with its row) and a look-alike (the same act done right, silent) per row."""
import importlib.util
import json
import os
import sys
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
     Record([READ_X]), pre("Write", file_path="/r/plan.md", content="Edit /r/a.py")),
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
    ("R14", Record([]), reply("This change saves tokens."),
     Record([]), reply("This change saves tokens. Delivery edge: child prompt; enabled-arm measured numerator: 20 tokens; bill denominator: $80.")),
]


@pytest.mark.parametrize("rid,prec,pev,lrec,lev", CASES, ids=[c[0] for c in CASES])
def test_plant_blocks_and_lookalike_silent(rows, rid, prec, pev, lrec, lev):
    if rid not in {r["id"] for r in rows} or (rid == "R04" and pev.get("tool_name") == NOTE) or rid == "R13":
        assert V.evaluate(rows, prec, pev) is None
        assert V.evaluate(rows, lrec, lev) is None
        return
    expected_row = rid
    if rid == "R05":
        pev = {"hook_event_name": "Stop", "claim": {"kind": "absent"}}
        lev = {"hook_event_name": "Stop", "claim": {"kind": "absent", "falsifier": "source result"}}
    elif rid == "R06":
        # A relayed number alone is not refs(output); the exact proxy is removed.
        assert V.evaluate(rows, prec, pev) is None
        assert V.evaluate(rows, lrec, lev) is None
        return
    elif rid == "R07":
        expected_row = "R08"
        quote = "the mesh is the chart"
        lrec = Record([Obs(1, "Read", {"ref": quote}, quote)])
    elif rid == "R08":
        lev = dict(lev, tree={"/r/a.py": {"hash": V.family_lineage.digest("x = 1")}})
    elif rid == "R12":
        expected_row = "R08"
        lev = dict(lev, cwd="/r", tree={"/r/docs/MAP.tsv": {"hash": V.family_lineage.digest("..")}})
    out = V.evaluate(rows, prec, pev)
    assert out is not None and out["row"] == expected_row, out
    assert out["objects"]
    assert ("REGISTRY-v9.md" if rid in ("R05", "R07", "R08", "R12") else "source:") in out["message"]
    assert V.evaluate(rows, lrec, lev) is None



def test_every_row_has_a_case_and_a_verbatim_source(rows):
    assert {r["id"] for r in rows} <= {c[0] for c in CASES}
    # sources.tsv pins each quote as found in MEMORY.md / WORDS.tsv, which live outside the repo
    pinned = {ln.split("\t")[0]: ln.rstrip("\n").split("\t")[2]
              for ln in open(os.path.join(TESTS, "sources.tsv"), encoding="utf-8").readlines()[1:] if ln.strip()}
    for r in rows:
        quoted = r["source"].split(': "', 1)[1].rsplit('"', 1)[0]
        assert pinned.get(r["id"]) == quoted, r["id"]


def test_config_keys_cover_config():
    keys = {ln.split("\t")[0] for ln in open(os.path.join(HERE, "CONFIG_KEYS.txt")) if ln.strip()}
    assert keys == set(json.load(open(os.path.join(HERE, "config.json"))))


"""Terminal witnesses bind status and content to the claimed subject."""
sys.path.insert(0, os.path.dirname(HERE))
from makoto2.evaluate import landed_owes, landed_pays
from makoto2.observed import record


def observation(output, *, tool='Bash', input=None, code=0):
    return record([dict(hook_event_name='PostToolUse', tool_name=tool,
                        tool_input=input or {}, tool_response=dict(stdout=output, exitCode=code))]).obs[0]


@pytest.mark.parametrize('output,paid', [
    ('FAILED test_charge\nsummary: passed', False),
    ('PASSED test_other\nsummary: passed', False),
    ('PASSED test_charge', True),
    ('{"charge":"failed","summary":"passed"}', False),
    ('{"charge":"passed"}', True),
    ('charge queued; validation passed', False),
    ('charge completed; validation passed', True),
])
def test_named_status(output, paid):
    o = observation(output)
    subjects = landed_owes({}, {'negation_window': 40}, record([]),
                           dict(hook_event_name='Stop', last_assistant_message='Charge passed.'))
    assert landed_pays({}, {}, o)(subjects[0]) == paid


@pytest.mark.parametrize('path,body,paid', [
    ('out/ledger.json', '', False),
    ('out/ledger.json', 'broken', False),
    ('out/ledger.json', '{}', False),
    ('out/ledger.json', '{"rows":[1]}', True),
    ('out/ledger.xml', '<ledger>', False),
    ('out/ledger.xml', '<ledger/>', False),
    ('out/ledger.xml', '<ledger><row>1</row></ledger>', True),
])
def test_artifact(path, body, paid):
    producer = observation('generated ' + path, input={'command': 'generate > ' + path})
    r = record([]); r.obs = [producer]
    subjects = landed_owes({}, {'negation_window': 40}, r,
                           dict(hook_event_name='Stop', last_assistant_message='Ledger is complete.'))
    assert not landed_pays({}, {}, producer)(subjects[0])
    reader = observation(body, tool='Read', input={'file_path': path})
    payment = landed_pays({}, {}, reader)
    assert bool(payment and payment(subjects[0])) == paid


def test_later_failure_invalidates_success():
    history = record([dict(hook_event_name='PostToolUse', tool_name='Bash',
                           tool_input={}, tool_response={'stdout': text})
                      for text in ('PASSED test_charge', 'FAILED test_charge\nsummary: passed')])
    subjects = landed_owes({}, {'negation_window': 40}, history,
                           dict(hook_event_name='Stop', last_assistant_message='Charge passed.'))
    assert not any(landed_pays({}, {}, o)(subjects[0]) for o in history.obs)


def test_launcher_success_is_not_job_success():
    o = observation('charge accepted; validation passed', input={'job': 'charge'}, tool='mcp__worker__launch')
    subjects = landed_owes({}, {'negation_window': 40}, record([]),
                           dict(hook_event_name='Stop', last_assistant_message='Charge passed.'))
    assert not landed_pays({}, {}, o)(subjects[0])


@pytest.mark.parametrize("command,output", [
    ("pytest -v", "FAILED tests/test_bill.py::test_charge - AssertionError"),
    ("python -m unittest -v", "FAIL: test_charge (tests.test_bill.Billing)"),
])
def test_counted_failure_keeps_its_subject(rows, command, output):
    record = Record([Obs(1, "Bash", {"command": command}, output, exit=1)])
    row = next(r for r in rows if r["id"] == "R11")
    plant = V.evaluate([row], record, reply("Twelve tests are failing."))
    assert plant and plant["row"] == "R11"
    assert V.evaluate([row], record, reply("One test failed: `test_charge`.")) is None


def test_failure_subject_fold_and_every_name(rows):
    row = next(r for r in rows if r["id"] == "R11")
    red = Obs(1, "Bash", {"command": "pytest"},
              "FAILED tests/a.py::test_one\nFAILED tests/b.py::test_two", exit=1)
    record = Record([red])
    assert V.evaluate([row], record, reply("Two tests failed: test_one."))
    assert V.evaluate([row], record, reply("Two tests failed: test_one, test_two.")) is None
    green = Obs(2, "Bash", {"command": "pytest"}, "PASSED tests/b.py::test_two")
    assert V.evaluate([row], Record([red, green]), reply("One test failed: test_one.")) is None
    log = red._replace(input={"command": "cat pytest.log"})
    assert V.evaluate([row], Record([log]), reply("Two tests failed.")) is None
    assert V.evaluate([row], record, reply("If two tests failed, list them.")) is None
    quoted = reply('The runner reports "two tests failed".')
    assert V.evaluate([row], record, quoted)["row"] == "R08"
    source = Obs(2, "Read", {"ref": "two tests failed"}, "two tests failed")
    assert V.evaluate([row], Record([red, source]), quoted) is None
