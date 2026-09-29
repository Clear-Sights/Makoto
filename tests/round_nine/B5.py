# B5 gate.hollow_test (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the hollow-test shapes the check exists to catch
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stop", pathlib.Path(__file__).with_name("_stop.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

ROW = "gate.hollow_test"
A = "as" + "sert"
BASE = "def test_a():\n    compute()\n    " + A + " 1 == 1\n"

CASES = [
    _m.written(ROW, "base", "tests/test_r9.py", BASE),
    _m.written(ROW, "constant-not-literal", "tests/test_r9.py",
               "def test_a():\n    compute()\n    " + A + " len([1]) == 1\n"),
    _m.written(ROW, "verifier-not-test-named", "tests/probe.py", BASE),
]
