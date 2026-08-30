"""Subprocess end-to-end for makoto/_dispatch_shim.sh — the shim itself, which the live-fire
smoke tests bypass (they invoke `python -m makoto.dispatch` directly). It pins the two
properties only the shim owns: (1) package resolution is pinned to the plugin root — a decoy
makoto/ package in the invoking cwd must not shadow it (under the former form it did:
ModuleNotFoundError exit 1 on every hook, a 100% failure rate on the marketplace install), and
(2) an unusable CLAUDE_PLUGIN_ROOT fails OPEN with a loud stderr line and an empty envelope,
matching dispatch's own HYBRID fail-mode. Runs against a bare venv interpreter so a dev
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
# The shim is invoked as ${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh, and CLAUDE_PLUGIN_ROOT
# is the installed subtree -- plugin/, not the repository root.
PLUGIN = REPO / "plugin"
SHIM = PLUGIN / "makoto" / "_dispatch_shim.sh"

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
    """The bit GIT records, not the one this checkout happens to have.

    `os.access(SHIM, os.X_OK)` reads the working tree, and git's mode is what an installing user
    receives: a local `chmod +x` passes this over an index recording 100644. Both are checked --
    the index because it ships, the working tree because the tests below have to run it.
    """
    done = subprocess.run(["git", "ls-files", "-s", "--", str(SHIM.relative_to(REPO))],
                          cwd=REPO, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and done.stdout.strip(), (
        f"git does not track {SHIM}; its recorded mode cannot be read, and absence is not a pass")
    mode = done.stdout.split()[0]
    assert mode == "100755", (
        f"git records mode {mode} for the shim; it must be 100755, because that is the bit an "
        f"installing user receives. A local chmod does not change it.")
    assert os.access(SHIM, os.X_OK), "the shim is not executable in this checkout"


def test_decoy_package_in_cwd_cannot_shadow_the_plugin(tmp_path, bare_python_dir):
    (tmp_path / "makoto").mkdir()
    (tmp_path / "makoto" / "__init__.py").write_text("")
    proc = _run_shim(cwd=tmp_path, state_dir=tmp_path / "state", env_overrides={
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
        "PATH": f"{bare_python_dir}{os.pathsep}{os.environ['PATH']}",
    })
    assert proc.returncode == 0, proc.stderr
    assert "No module named" not in proc.stderr, proc.stderr
    # EVIDENCE THE REAL MODULE RAN, not just that something exited 0. Both assertions above are
    # satisfied by a shim replaced with `exit 0`, which is the opposite of what this test is
    # named for: it claims resolution reached the plugin's own package. `makoto.dispatch` opens
    # its record database in MAKOTO_STATE_DIR on any event, and a stub creates nothing there.
    assert (tmp_path / "state" / "makoto.record.db").is_file(), (
        f"the shim exited 0 and left no record database in {tmp_path / 'state'}; nothing shows "
        f"makoto.dispatch was resolved and executed, which is the whole claim here. "
        f"stdout={proc.stdout[:300]!r} stderr={proc.stderr[-300:]!r}")


def test_unusable_plugin_root_fails_open_loudly(tmp_path):
    proc = _run_shim(cwd=tmp_path, state_dir=tmp_path / "state", env_overrides={})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "{}"
    assert "failing open" in proc.stderr
