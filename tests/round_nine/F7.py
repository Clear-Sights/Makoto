# F7 gate.stale_pass (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the pass claims the check exists to hold against the record
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stale", pathlib.Path(__file__).with_name("_stale.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

CASES = [
    _m.case("base", "All tests " + "pass now."),
    # the claim names the very node pytest's record holds as failing
    _m.case("node", "test_red " + "passes now."),
    # a universal claim with no test noun in it
    _m.case("everything", "Everything is " + "green."),
]
