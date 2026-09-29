# Shared builder for the gate.undeclared_falsifiable entries (C2, B32); underscore: not a case module.
# Each case copies this tree's plugin package into the case cwd and plants into the COPY.
import shutil
from pathlib import Path

ROW = "gate.undeclared_falsifiable"
SRC = Path(__file__).resolve().parents[2] / "plugin" / "makoto"
STOP = {"hook_event_name": "Stop", "last_assistant_message": "Done."}


def _copy(cwd):
    """Copy the plugin package under the case cwd; the case's planted files (written first) are
    kept over the originals. Python, not `cp -rn`: the runner's shell is cmd.exe on Windows."""
    dst = Path(cwd) / "plugin" / "makoto"
    for src in SRC.rglob("*"):
        rel = src.relative_to(SRC)
        if "__pycache__" in rel.parts or not src.is_file():
            continue
        out = dst / rel
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out)


def row_module(run):
    return ("from makoto.registry import Check\n"
            f"CHECK = Check(id='content.newrow', applies_at='Stop', posture='BLOCK', run={run})\n")


def case(name, files=None, then=None):
    files = {f"plugin/makoto/checks/{k}": v for k, v in (files or {}).items()}

    def setup(cwd):
        _copy(cwd)
        if then:
            then(Path(cwd))
    return dict(name=name, row=ROW, files=files, setup=setup, events=[STOP])
