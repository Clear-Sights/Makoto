# B1 gate.self_wired (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the hook-disabling shapes the check exists to catch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wiring import case, settings  # noqa: E402

CASES = [
    case("base", settings(drop=("PostToolUse",))),
    case("disable-all-hooks", settings(**{"disable" + "AllHooks": True})),
    case("matcher-no-tool", settings(matcher={"PreToolUse": "NoSuchTool", "PostToolUse": "NoSuchTool"})),
]
