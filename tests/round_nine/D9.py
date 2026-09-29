# D9 gate.self_wired (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the unreachable-wiring shapes the check exists to catch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wiring import INV, case, settings  # noqa: E402

CASES = [
    case("base", settings(drop=("PreToolUse",))),
    case("matcher-no-such-tool", settings(matcher={"PostToolUse": "NoSuchTool"})),
    case("or-short-circuit", settings(command={"PostToolUse": "tr" + "ue || " + INV})),
]
