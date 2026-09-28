#!/usr/bin/env python3
"""Dedupe the entries both Scour and Makoto own, by the MERGE-WITNESSES rule (START step 12): one
owner survives only when its fix alone catches the other's trip. Each side's catch case is run
through the OTHER side: Scour at its pin reads Makoto's case as a tree, and Makoto's dispatcher reads
Scour's case as the Write events that would create it. A side that stays silent on the other's case
is a witness that the two are not one entry's duplicate: they own different facets (Scour the
tree, Makoto the event) and both stay.

usage: python3 tools/dedupe.py      prints one DEDUPE row per entry; exits 2 when Scour is absent
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import owners  # noqa: E402  (SCOUR_PIN, missing)

REGISTER_PIN = next(ln.split("=", 1)[1].strip() for ln in (REPO / "tools" / "scour.sh").read_text().splitlines()
                    if ln.startswith("REGISTER_PIN="))
_REPAIR = "if timeout is None:\n    timeout = DEFAULT_TIMEOUT\nif timeout < 0:\n    raise ValueError(timeout)\n"
# entry -> (Makoto's runner, Makoto's catch case: path -> text written, or (old, new) for an Edit)
MAKOTO = {
    "B2": ("gate.hollow_test", {"tests/test_a.py": "def test_a():\n    x = compute()\n"}),
    "B7": ("content.rule_without_runner", {"CLAUDE.md": "# Rules\n- Always run the linter before committing.\n"}),
    "F2": ("gate.pasted_fix", {"src/reader.py": ("pass\n", _REPAIR), "src/writer.py": ("pass\n", _REPAIR)}),
}


def _clone(names):
    return next((p for p in (REPO.parent / n for n in names) if p.is_dir()), None)


def _scour_env():
    s, m = _clone(("Scour", "scour")), _clone(("Measure-Zero", "measure-zero"))
    if s is None or m is None:
        owners.missing("clone Clear-Sights/Scour and Clear-Sights/Measure-Zero beside this repository")
    d = Path(tempfile.mkdtemp())
    tar = subprocess.run(["git", "-C", str(s), "archive", owners.SCOUR_PIN], capture_output=True)
    reg = subprocess.run(["git", "-C", str(m), "show", f"{REGISTER_PIN}:zero/resources/REGISTER.md"],
                         capture_output=True)
    if tar.returncode or reg.returncode:
        owners.missing(f"fetch Scour {owners.SCOUR_PIN} and Measure-Zero {REGISTER_PIN}")
    tarfile.open(fileobj=io.BytesIO(tar.stdout)).extractall(d / "scour", filter="data")
    (d / "REGISTER.md").write_bytes(reg.stdout)
    return d


def scour_fires(env: Path, entry: str, files: dict) -> bool:
    tree = Path(tempfile.mkdtemp())
    for rel, text in files.items():
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_text(text[1] if isinstance(text, tuple) else text, encoding="utf-8")
    detail = Path(tempfile.mkdtemp()) / "detail.txt"
    subprocess.run([sys.executable, "-m", "scour", str(tree), "--register", str(env / "REGISTER.md"),
                    "--detail", str(detail)], cwd=env / "scour", capture_output=True, text=True)
    body = detail.read_text(encoding="utf-8").split("entries no static pass")[0]
    return bool(re.search(rf"^{entry}\s", body, re.M))


def makoto_fires(runner: str, files: dict) -> bool:
    """Drive the real dispatcher: each file arrives as a Pre then Post Write (or Edit), then a Stop."""
    tmp = Path(tempfile.mkdtemp())
    env = {**os.environ, "MAKOTO_STATE_DIR": str(tmp / "state"), "PYTHONPATH": str(REPO / "plugin")}
    out = []

    def send(ev):
        r = subprocess.run([sys.executable, "-m", "makoto.dispatch"], input=json.dumps(ev), text=True,
                           capture_output=True, cwd=REPO / "plugin", env=env)
        out.append(r.stdout + r.stderr)
    for rel, text in files.items():
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, tuple):
            (tmp / rel).write_text(text[0], encoding="utf-8")
            base = {"session_id": "dedupe", "cwd": str(tmp), "tool_name": "Edit",
                    "tool_input": {"file_path": str(tmp / rel), "old_string": text[0].strip(),
                                   "new_string": text[1]}}
            text = text[1]
        else:
            base = {"session_id": "dedupe", "cwd": str(tmp), "tool_name": "Write",
                    "tool_input": {"file_path": str(tmp / rel), "content": text}}
        send({**base, "hook_event_name": "PreToolUse"})
        (tmp / rel).write_text(text, encoding="utf-8")
        send({**base, "hook_event_name": "PostToolUse", "tool_response": {}})
    send({"hook_event_name": "Stop", "session_id": "dedupe", "cwd": str(tmp), "last_assistant_message": "Done."})
    return runner in "".join(out)


def scour_case(entry: str) -> dict:
    sys.path.insert(0, str(_scour_root))
    import scour.probes as P
    return next(p.yes for p in P.catalogue() if p.id == entry)


def main() -> int:
    global _scour_root
    env = _scour_env()
    _scour_root = env / "scour"
    bad = 0
    for entry, (runner, mk_case) in MAKOTO.items():
        sc_case = scour_case(entry)
        own = (scour_fires(env, entry, sc_case), makoto_fires(runner, mk_case))
        cross = (scour_fires(env, entry, mk_case), makoto_fires(runner, sc_case))
        if not all(own):
            verdict = "NOT-EVALUABLE: a side is silent on its own case"
            bad = 1
        elif cross == (False, False):
            verdict = "keep both: each is silent on the other's trip, so they own different facets"
        else:
            verdict = ("drop Makoto's: Scour catches both trips" if cross[0] and not cross[1]
                       else "drop Scour's: Makoto catches both trips" if cross[1] and not cross[0]
                       else "one entry: each catches the other's trip; keep the event side (PRIOR-ART item 2)")
        print(f"DEDUPE {entry}\t{runner}\tscour_on_makoto_case={cross[0]}\tmakoto_on_scour_case={cross[1]}\t{verdict}")
    return bad


if __name__ == "__main__":
    sys.exit(main())
