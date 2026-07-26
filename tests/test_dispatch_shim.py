"""Subprocess end-to-end for makoto/_dispatch_shim.sh — the shim itself, which the live-fire
smoke tests bypass (they invoke `python -m makoto._dispatch` directly). It pins the two
properties only the shim owns: (1) package resolution is pinned to the plugin root — a decoy
makoto/ package in the invoking cwd must not shadow it (under the former form it did:
ModuleNotFoundError exit 1 on every hook, a 100% failure rate on the marketplace install), and
(2) an unusable CLAUDE_PLUGIN_ROOT fails OPEN with a loud stderr line and an empty envelope,
matching _dispatch's own HYBRID fail-mode. Runs against a bare venv interpreter so a dev
editable install cannot mask a resolution failure — with the dev interpreter these checks could
never return FALSE."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SHIM = REPO / "makoto" / "_dispatch_shim.sh"

EVENT = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
         "tool_input": {"command": "ls"}, "session_id": "shim-test",
         "transcript_path": "/tmp/does-not-exist.jsonl"}


@pytest.fixture(scope="module")
def bare_python_dir(tmp_path_factory) -> Path:
    """A venv without makoto installed: resolution can only come from the shim's own cwd pin."""
    env_dir = tmp_path_factory.mktemp("bare-venv")
    venv.create(env_dir, with_pip=False)
    return env_dir / ("Scripts" if sys.platform == "win32" else "bin")


def _run_shim(cwd: Path, env_overrides: dict, state_dir: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_ROOT", "PYTHONPATH")}
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    env.update(env_overrides)
    return subprocess.run([str(SHIM)], input=json.dumps(EVENT), text=True,
                          capture_output=True, cwd=cwd, env=env, timeout=30)


def test_shim_is_executable():
    assert os.access(SHIM, os.X_OK)


def test_decoy_package_in_cwd_cannot_shadow_the_plugin(tmp_path, bare_python_dir):
    (tmp_path / "makoto").mkdir()
    (tmp_path / "makoto" / "__init__.py").write_text("")
    proc = _run_shim(cwd=tmp_path, state_dir=tmp_path / "state", env_overrides={
        "CLAUDE_PLUGIN_ROOT": str(REPO),
        "PATH": f"{bare_python_dir}{os.pathsep}{os.environ['PATH']}",
    })
    assert proc.returncode == 0, proc.stderr
    assert "No module named" not in proc.stderr, proc.stderr


def test_unusable_plugin_root_fails_open_loudly(tmp_path):
    proc = _run_shim(cwd=tmp_path, state_dir=tmp_path / "state", env_overrides={})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "{}"
    assert "failing open" in proc.stderr
