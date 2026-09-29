# C2 gate.undeclared_falsifiable (docs/attack-round-nine.md, round nine).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _catalog import case, row_module  # noqa: E402

CASES = [
    case("base", {"stray.py": "VALUE = 1\n"}),
    case("undeclared-run-none", {"newrow.py": row_module("lambda ctx=None: None")}),
]
