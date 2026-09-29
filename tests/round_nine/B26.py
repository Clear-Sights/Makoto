# B26 gate.self_wired (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the gutted-invocation shapes the check exists to catch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wiring import INV, case, settings  # noqa: E402

CASES = [
    case("base", settings(drop=("Stop",))),
    case("gutted-or", settings(command={"Stop": "tr" + "ue || " + INV})),
    case("echo-invocation", settings(command={"Stop": "ec" + "ho " + INV})),
]
