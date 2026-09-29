# D4 gate.stale_pass (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the pass claims the check exists to hold against the record
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stale", pathlib.Path(__file__).with_name("_stale.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

CLAIM = "All tests " + "pass now."
RUN = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
       "tool_input": {"command": "python3 -m pytest -q"},
       "tool_response": {"stdout": "...\n3 passed in 0.12s\n", "stderr": "", "interrupted": False}}
EDIT = {"hook_event_name": "PostToolUse", "tool_name": "Edit",
        "tool_input": {"file_path": "{cwd}/src/app.py", "old_string": "return 1",
                       "new_string": "return 2"},
        "tool_response": {}}

CASES = [
    _m.case("base", CLAIM),
    # a green run recorded, then the source edited after it: the pass is older than the source
    dict(name="newer-source", row=_m.ROW,
         files=dict(_m.cache({}), **{"src/app.py": "def f():\n    return 2\n"}),
         events=[RUN, EDIT, _m.stop(CLAIM)]),
    # the session sits in a subdirectory; pytest's record is at the project root
    _m.case("subdir-cwd", CLAIM, cwd="{cwd}/tests"),
]
