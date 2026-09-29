# H2 gate.stale_pass (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the pass claims the check exists to hold against the record
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stale", pathlib.Path(__file__).with_name("_stale.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

CLAIM = "All tests " + "pass now."
GONE = {f"tests/a_gone_{i:02d}.py::test_x": True for i in range(60)}

CASES = [
    _m.case("base", CLAIM),
    # the session's cwd is the repo's tests/ subdirectory; the record is at the repo root
    dict(_m.case("tests-cwd", CLAIM, cwd="{cwd}/tests"), setup="git init -q"),
    # 60 deleted-test nodes sort ahead of the one live failing node
    _m.case("deleted-ahead", CLAIM, entries=dict(GONE, **{_m.NODE: True})),
]
