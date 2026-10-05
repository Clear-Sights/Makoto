"""Fixes from the seed-run branch (#133) that a conflict resolution dropped."""
import os, sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))
from makoto2 import hook, observed


def _obs(output):
    return SimpleNamespace(seq=3, tool="Bash", input={"command": "pytest"}, output=output,
                           exit=0, failed=False, objects={"t.py"}, written=set(),
                           created=set(), send="", search=None)


def test_changed_result_at_same_offset_fires_again():
    finding = {"row": "R1", "objects": ["t.py"]}
    _, first = hook.o_once(finding, SimpleNamespace(obs=[_obs("1 failed")]), set())
    found, second = hook.o_once(finding, SimpleNamespace(obs=[_obs("1 passed")]), {first})
    assert found is finding and second != first


def test_current_settled_event_joins_the_record():
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
          "tool_input": {"command": "ls"}, "tool_response": {"stdout": "a", "exit_code": 0}}
    assert len(observed.record([], ev).obs) == 1
    assert len(observed.record([], dict(ev, hook_event_name="PreToolUse")).obs) == 0
