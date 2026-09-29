# B32 gate.undeclared_falsifiable (docs/attack-round-nine.md, round nine).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _catalog import case, row_module  # noqa: E402

UNROUTE = ("python3 -c \"import pathlib; p = pathlib.Path('plugin/makoto/checks/spec.py'); "
           "p.write_text(p.read_text().replace('rule_runner_CHECK.id: rule_runner_predicate, ', '', 1))\"")

CASES = [
    case("base", {"stray.py": "VALUE = 1\n"}),
    case("newrow-undeclared", {"newrow.py": row_module("lambda c: None")}),
    case("declared-row-unrouted", then=UNROUTE),
    # Importing this module ends the importing process silently; only a catalog READ, never an
    # import, can still see its undeclared row.
    case("unimportable-module-read-not-run",
         {"newrow.py": "import os\nos._exit(0)\n" + row_module("lambda c: c")}),
]
