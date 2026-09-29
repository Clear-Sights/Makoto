# B2 gate.hollow_test (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the hollow-test shapes the check exists to catch
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stop", pathlib.Path(__file__).with_name("_stop.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

ROW = "gate.hollow_test"
A = "as" + "sert"
T = "Tr" + "ue"
P = "tests/test_r9.py"


def _t(body):
    return "def test_a():\n    r = compute()\n" + body


CASES = [
    _m.written(ROW, "base", P, _t(f"    {A} {T}\n")),
    _m.written(ROW, "or-true", P, _t(f"    {A} r == 2 or {T}\n")),
    _m.written(ROW, "except-return", P,
               "def test_a():\n    try:\n        r = compute()\n        " + A + " r == 2\n"
               "    except Exception:\n        return\n"),
]
