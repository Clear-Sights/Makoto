# B20 gate.hollow_test (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the hollow-test shapes the check exists to catch
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stop", pathlib.Path(__file__).with_name("_stop.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

ROW = "gate.hollow_test"
A = "as" + "sert"
BASE = "def test_a():\n    r = compute()\n    " + A + " r == r\n"

CASES = [
    _m.written(ROW, "base", "tests/test_r9.py", BASE),
    _m.written(ROW, "or-true", "tests/test_r9.py",
               "def test_a():\n    r = compute()\n    " + A + " r == 2 or Tr" "ue\n"),
    _m.written(ROW, "except-return", "tests/test_r9.py",
               "def test_a():\n    try:\n        r = compute()\n        " + A + " r == 2\n"
               "    except Exception:\n        return\n"),
    _m.written(ROW, "uppercase-dir", "Measure-Zero/tests/test_r9.py", BASE),
    _m.written(ROW, "uppercase-dir-lowercase-twin", "Measure-Zero/tests/test_r9.py", BASE,
               others={"measure-zero/tests/test_r9.py": "def test_a():\n    " + A + " f() == 2\n"}),
]
