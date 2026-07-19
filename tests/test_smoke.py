"""Public-artifact smoke test: the ONE test file the public repo ships (public-scope decision,
2026-07-10: public carries the runtime a consumer uses plus what they are meant to read; the
full falsifiability suite lives in makoto-dev). Self-contained -- no conftest fixtures -- and
end-to-end: it drives the REAL dispatch subprocess a Claude Code hook would, asserting on the
exact wire shapes captured live (a PreToolUse block is rc=0 + hookSpecificOutput
permissionDecision "deny"; a clean event is rc=0 + empty stdout). Dev runs it too, so the
shipped smoke can never silently rot relative to the mechanism it certifies."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _dispatch(payload: dict, state_dir: Path):
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run([sys.executable, "-m", "makoto._dispatch"],
                          input=json.dumps(payload).encode(), capture_output=True, env=env)
    return proc.returncode, proc.stdout.decode()


def _state(tmp_path: Path) -> Path:
    from makoto.record.db import init_db
    state = tmp_path / "state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n")
    init_db(state, citations)
    return state


def test_catalog_loads_nonempty():
    from makoto.core.schema import load_prechecks
    from makoto.substrate._loader import load_checks
    assert load_prechecks(), "Pre-tier catalog discovered"
    assert load_checks(edge="Stop"), "Stop-tier catalog discovered"


def test_install_wires_hooks_and_records_manifest(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    from makoto.install import cmd_install
    assert cmd_install() == 0
    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    wired = json.dumps(settings.get("hooks", {})).lower()
    assert "makoto" in wired, "install must wire a makoto-dispatching hook entry"
    manifest = fake_home / ".claude" / "makoto_state" / "configchange_manifest.json"
    assert manifest.exists(), "install must record the ConfigChange manifest"


def test_env_gated_audit_is_denied_on_the_wire(tmp_path):
    # forbiddenLocation moved to Ward, 2026-07-13 (github.com/Clear-Sights/Ward) -- content.env_gated_audit
    # is the still-live substitute exercising the same PreToolUse-Write-deny wire shape.
    state = _state(tmp_path)
    rc, out = _dispatch({"hook_event_name": "PreToolUse", "session_id": "smoke-block",
                         "cwd": str(tmp_path), "tool_name": "Write",
                         "tool_input": {"file_path": str(tmp_path / "app.py"),
                                       "content": "if os.environ.get('ENABLE_AUDIT_TRAIL'):\n"
                                                  "    write_audit_trail()\n"},
                         "tool_use_id": "t1"}, state)
    assert rc == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "env" in decision["permissionDecisionReason"].lower()


def test_benign_write_passes_silently(tmp_path):
    state = _state(tmp_path)
    rc, out = _dispatch({"hook_event_name": "PreToolUse", "session_id": "smoke-clean",
                         "cwd": str(tmp_path), "tool_name": "Write",
                         "tool_input": {"file_path": str(tmp_path / "ok.py"), "content": "x = 1\n"},
                         "tool_use_id": "t2"}, state)
    assert rc == 0 and out == ""


def test_clean_stop_passes_silently(tmp_path):
    state = _state(tmp_path)
    rc, out = _dispatch({"hook_event_name": "Stop", "session_id": "smoke-stop",
                         "cwd": str(tmp_path),
                         "last_assistant_message": "Read through the module as asked."}, state)
    assert rc == 0 and out == ""


def test_readme_references_exist():
    """Every relative path the README embeds or links must exist in this tree — a landing page
    that shows broken images or dead links is a said-but-not-shipped artifact (the exact shape
    this suite exists to block). Regression: docs/demo/ was referenced for weeks while never
    committed."""
    import re
    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text()
    refs = re.findall(r'<img src="([^"]+)"', readme)
    refs += [m for m in re.findall(r"\]\(([^)]+)\)", readme)
             if not m.startswith(("http://", "https://", "#", "mailto:"))]
    missing = [r for r in refs if not (root / r.split("#")[0]).exists()]
    assert not missing, f"README references missing files: {missing}"
