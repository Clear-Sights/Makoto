"""docs/demo/render_demo.py — drive 3 REAL scenarios through the actual dispatchers.

Each scenario runs the real `python -m makoto._dispatch` / `python -m makoto._dispatch_configchange`
/ `python -m makoto receipt` against a fresh, throwaway MAKOTO_STATE_DIR and captures the genuine
stdout/stderr/exit of every step into `docs/demo/logs/<scenario>.json`. Nothing here is mocked or
hand-written: the EVENTS are scripted (it is a synthetic session), the DISPATCHERS and their output
are the real ones — the same fail-open, block, redirect and receipt paths production runs.

Scenarios (matching the README's "Live demo" section):
  block        — a PreToolUse Write loosening a verifier comparator; makoto denies the call.
  receipt      — word -> deed -> record -> receipt: a touched file, a FAILED test run, a fix, a
                 PASSED rerun (the test-delta redirect fires and is chain-appended), a clean Stop
                 claim, then `makoto receipt --session demo-session-001`.
  configchange — a `.claude/settings.json` edit that strips makoto's hooks with no wiring
                 evidence on record; the ConfigChange watch logs its ADVISORY and allows.

Run from the repo root:  python docs/demo/render_demo.py
Then render the SVGs:    python docs/demo/render_svg.py   (needs `humanize`; see its docstring)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEMO_DIR = Path(__file__).parent
LOGS_DIR = DEMO_DIR / "logs"


def _run(module: list, payload: dict | None, state_dir: Path, display_cmd: str, title: str) -> dict:
    """Run one real dispatcher step; capture its genuine exit/stdout/stderr."""
    env = dict(os.environ, MAKOTO_STATE_DIR=str(state_dir))
    proc = subprocess.run(
        [sys.executable, "-m", *module],
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True, text=True, env=env,
    )
    return {"title": title, "display_cmd": display_cmd, "payload": payload,
            "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _log(scenario: str, steps: list) -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    out = LOGS_DIR / f"{scenario}.json"
    out.write_text(json.dumps({"scenario": scenario, "steps": steps}, indent=1))
    print(f"wrote {out} ({len(steps)} steps)")


def scenario_block(tmp: Path) -> None:
    """A genuine PreToolUse block: the agent tries to loosen a verifier comparator."""
    state = tmp / "block-state"
    proj = tmp / "block-proj"
    proj.mkdir(parents=True)
    steps = [_run(["makoto._dispatch"], {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "demo-block-001",
        "cwd": str(proj),
        "tool_input": {
            "file_path": str(proj / "constitution/integrity/checks/release_gate.py"),
            "content": 'def check(status):\n    return status.startswith("ok")\n',
        },
    }, state, "PreToolUse Write constitution/integrity/checks/release_gate.py",
        "the agent tries to loosen a verifier (== -> startswith)")]
    _log("block", steps)


def scenario_receipt(tmp: Path) -> None:
    """word -> deed -> record -> receipt, end to end, one synthetic session."""
    state = tmp / "receipt-state"
    proj = tmp / "receipt-proj"
    proj.mkdir(parents=True)
    sid = "demo-session-001"

    def post_write(content: str, title: str) -> dict:
        return _run(["makoto._dispatch"], {
            "hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": sid,
            "cwd": str(proj),
            "tool_input": {"file_path": str(proj / "src/auth.py"), "content": content},
            "tool_response": {"filePath": str(proj / "src/auth.py")},
        }, state, "PostToolUse Write src/auth.py", title)

    def post_pytest(stdout: str, exit_code: int, title: str) -> dict:
        return _run(["makoto._dispatch"], {
            "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
            "cwd": str(proj),
            "tool_input": {"command": "python -m pytest tests/test_auth.py -q -rA"},
            "tool_response": {"stdout": stdout, "stderr": "", "exitCode": exit_code},
        }, state, "PostToolUse Bash `python -m pytest tests/test_auth.py -q -rA`", title)

    steps = [
        post_write("def login(user):\n    return None\n",
                   "WORD becomes deed: the write lands (kind=touched, chain row 1)"),
        post_pytest(
            "F                                                                    [100%]\n"
            "FAILED tests/test_auth.py::test_login - AssertionError: expected a session token\n"
            "=== 1 failed in 0.14s ===\n", 1,
            "a real test run FAILS (kind=testrun, chain row 2)"),
        post_write("def login(user):\n    return session_token(user)\n",
                   "the fix lands (kind=touched)"),
        post_pytest(
            ".                                                                    [100%]\n"
            "PASSED tests/test_auth.py::test_login\n"
            "=== 1 passed in 0.06s ===\n", 0,
            "the rerun PASSES — the test-delta redirect fires and is ITSELF chain-appended (kind=audit)"),
        _run(["makoto._dispatch"], {
            "hook_event_name": "Stop", "session_id": sid, "cwd": str(proj),
            "last_assistant_message": "Fixed src/auth.py — test_login passes now. Done.",
        }, state, "Stop", "the closing claim is checked against the recorded ledger: clean, allowed"),
        _run(["makoto", "receipt", "--session", sid], None, state,
             f"python -m makoto receipt --session {sid}",
             "RECEIPT: every claim cites a verify_chain-checkable row"),
    ]
    _log("receipt", steps)


def scenario_configchange(tmp: Path) -> None:
    """The ConfigChange watch: a settings edit that looks stripped, with no wiring evidence."""
    state = tmp / "configchange-state"
    proj = tmp / "configchange-proj"
    (proj / ".claude").mkdir(parents=True)
    settings = proj / ".claude" / "settings.json"
    settings.write_text(json.dumps(
        {"hooks": {"PreToolUse": [], "PostToolUse": [], "Stop": []}}, indent=1))
    steps = [_run(["makoto._dispatch_configchange"], {
        "hook_event_name": "ConfigChange",
        "session_id": "demo-configchange-001",
        "cwd": str(proj),
        "config_source": "project_settings",
        "config_path": str(settings),
    }, state, "ConfigChange .claude/settings.json (makoto hooks absent)",
        "no evidence this path was ever wired -> ADVISORY only, never a block")]
    _log("configchange", steps)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="makoto-demo-") as t:
        tmp = Path(t)
        scenario_block(tmp)
        scenario_receipt(tmp)
        scenario_configchange(tmp)


if __name__ == "__main__":
    main()
