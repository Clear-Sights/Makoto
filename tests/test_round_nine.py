"""Round nine's proving set (START step 13, docs/attack-round-nine.md): each escape rebuilt from
its shape as a plant. A case is a list of hook events fed in order to `python3 -m makoto.dispatch`
with fresh state, cwd and HOME, as the attack did; it passes when its entry's row names itself in
the output of the event at `at` (default: the last). Main let every case through, so each read red
there. Cases live one module per entry in tests/round_nine/, as CASES lists of dicts:

    name, row, events; optional files {relpath: text} under the case cwd, home {relpath: text}
    under the case HOME, setup (a shell line run in the cwd first, or a function taking the cwd
    Path), at (event index).

`{cwd}` and `{home}` inside any string are replaced with the case's directories."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_PLUGIN = _HERE.parent / "plugin"


def _load():
    cases = []
    for mod in sorted((_HERE / "round_nine").glob("*.py")):
        if mod.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"round_nine_{mod.stem}", mod)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        for c in m.CASES:
            cases.append(pytest.param(c, id=f"{mod.stem}-{c['name']}"))
    return cases


CASES = _load()


def _fill(obj, cwd: str, home: str):
    if isinstance(obj, str):
        return obj.replace("{cwd}", cwd).replace("{home}", home)
    if isinstance(obj, list):
        return [_fill(x, cwd, home) for x in obj]
    if isinstance(obj, dict):
        return {k: _fill(v, cwd, home) for k, v in obj.items()}
    return obj


def run_case(case: dict, root: Path) -> list[str]:
    """Feed the case's events in order; return each event's dispatcher stdout."""
    cwd, home, state = root / "work", root / "home", root / "state"
    for d in (cwd, home, state):
        d.mkdir(parents=True, exist_ok=True)
    for base, files in ((cwd, case.get("files", {})), (home, case.get("home", {}))):
        for rel, text in files.items():
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_fill(text, str(cwd), str(home)))
    if callable(case.get("setup")):
        case["setup"](cwd)
    elif case.get("setup"):
        subprocess.run(_fill(case["setup"], str(cwd), str(home)), shell=True, cwd=cwd,
                       check=True, capture_output=True)
    env = dict(os.environ, MAKOTO_STATE_DIR=str(state), HOME=str(home))
    outs = []
    for ev in case["events"]:
        ev = _fill(dict({"session_id": "r9", "cwd": str(cwd)}, **ev), str(cwd), str(home))
        p = subprocess.run([sys.executable, "-m", "makoto.dispatch"], input=json.dumps(ev).encode(),
                           capture_output=True, env=env, cwd=str(_PLUGIN))
        assert p.returncode == 0, p.stderr.decode(errors="replace")
        outs.append(p.stdout.decode())
    return outs


def test_cases_exist():
    assert len(CASES) > 0


@pytest.mark.parametrize("case", CASES)
def test_escape_is_caught(case, tmp_path):
    outs = run_case(case, tmp_path)
    out = outs[case.get("at", -1)]
    assert f"makoto: row {case['row']} " in out, f"{case['row']} let it through: {out[:300]!r}"
