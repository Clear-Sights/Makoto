# H6 gate.unclaimed_unit (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the unclaimed-unit shapes the check exists to catch
import importlib.util
import pathlib

_s = importlib.util.spec_from_file_location("_r9_stop", pathlib.Path(__file__).with_name("_stop.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)

ROW = "gate.unclaimed_unit"
P = "src/helpers.py"

CASES = [
    _m.written(ROW, "base", P, "def helper(a):\n    return a + 1\n"),
    _m.written(ROW, "own-docstring-names-it", P,
               'def helper(a):\n    """helper adds one."""\n    return a + 1\n'),
    _m.written(ROW, "functools-cache", P,
               "import functools\n\n\n@functools.cache\ndef helper(a):\n    return a + 1\n"),
]
