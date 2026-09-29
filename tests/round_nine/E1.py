# E1 gate.liveness (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the dead-store shapes the check exists to catch
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stop", pathlib.Path(__file__).with_name("_stop.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

ROW = "gate.liveness"
BASE = "def f(a):\n    x = 1 + 2\n    return a\n\n\nprint(f(1))\n"

CASES = [
    _m.written(ROW, "base", "src/m.py", BASE),
    _m.written(ROW, "killed-by-rebind", "src/m.py",
               "def f(a):\n    x = 1 + 2\n    x = a\n    return x\n\n\nprint(f(1))\n"),
    _m.written(ROW, "module-level-expr", "src/m.py", "print(2)\n1 + 2\n"),
    _m.written(ROW, "uppercase-dir", "Measure-Zero/src/m.py", BASE),
    _m.written(ROW, "uppercase-dir-lowercase-twin", "Measure-Zero/src/m.py", BASE,
               others={"measure-zero/src/m.py": "X = 1\n"}),
]
