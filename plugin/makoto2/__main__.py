"""Entry: python3 -m makoto2 < hook payload. Wires C, W, R, V into hook.main (the equation)."""
import json, os, sys
from makoto2 import hook, observed, evaluate

def run():                                       # the equation, once per hook call
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = evaluate.load_cfg(os.path.join(here, "config.json"))
    cfg["state_dir"] = os.path.expanduser(os.environ.get("MAKOTO_STATE_DIR") or cfg["state_dir"])
    rows = evaluate.load_rows(os.path.join(here, "rows.tsv"), cfg)
    sys.stdout.write(json.dumps(hook.main(sys.stdin.read(), cfg, rows, observed.record, evaluate.evaluate)))
    return 0

if __name__ == "__main__":
    sys.exit(run())
