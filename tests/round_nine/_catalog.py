# Shared builder for the gate.undeclared_falsifiable entries (C2, B32); underscore: not a case module.
# Each case copies this tree's plugin package into the case cwd and plants into the COPY.
import shlex
from pathlib import Path

ROW = "gate.undeclared_falsifiable"
SRC = Path(__file__).resolve().parents[2] / "plugin" / "makoto"
STOP = {"hook_event_name": "Stop", "last_assistant_message": "Done."}
# `-n`: the case's planted files (written first) are kept over the originals.
COPY = (f"mkdir -p plugin/makoto && cp -rn {shlex.quote(str(SRC))}/. plugin/makoto/"
        " && find plugin -name __pycache__ -prune -exec rm -rf {} +")


def row_module(run):
    return ("from makoto.registry import Check\n"
            f"CHECK = Check(id='content.newrow', applies_at='Stop', posture='BLOCK', run={run})\n")


def case(name, files=None, then=""):
    files = {f"plugin/makoto/checks/{k}": v for k, v in (files or {}).items()}
    return dict(name=name, row=ROW, files=files, setup=COPY + (" && " + then if then else ""),
                events=[STOP])
