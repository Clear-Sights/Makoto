"""Every input-consuming entry point refuses missing, empty, and malformed input."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _run(argv: list[str], raw: bytes, *, env: dict | None = None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(argv, input=raw, capture_output=True, cwd=REPO, env=full_env)


def test_dispatchers_refuse_missing_empty_and_malformed_stdin(tmp_path):
    """No hook adapter may turn a missing or malformed envelope into a green result."""
    matrix = {
        "dispatch": [sys.executable, "-m", "makoto._dispatch"],
        "configchange": [sys.executable, "-m", "makoto._dispatch_configchange"],
        "dispatch-shim": [str(REPO / "makoto" / "_dispatch_shim.sh")],
        "configchange-shim": [str(REPO / "makoto" / "_dispatch_configchange_shim.sh")],
    }
    cases = {"missing": b"", "empty": b"{}", "malformed": b"{not json"}
    for name, argv in matrix.items():
        for case, raw in cases.items():
            proc = _run(argv, raw, env={
                "MAKOTO_STATE_DIR": str(tmp_path / name / case),
                "CLAUDE_PLUGIN_ROOT": str(REPO),
            })
            assert proc.returncode == 2, (name, case, proc.returncode, proc.stderr)
            assert proc.stderr, (name, case, "must explain the refusal")


def test_cli_required_arguments_refuse_missing_empty_and_malformed_forms():
    """The argument parser gives its input contract the same exit-2 refusal semantics."""
    cases = {
        "missing-command": [sys.executable, "-m", "makoto"],
        "empty-show-key": [sys.executable, "-m", "makoto", "show"],
        "blank-show-key": [sys.executable, "-m", "makoto", "show", ""],
        "blank-pattern-id": [sys.executable, "-m", "makoto", "pattern", "show", ""],
        "blank-receipt-session": [sys.executable, "-m", "makoto", "receipt", "--session", ""],
        "malformed-command": [sys.executable, "-m", "makoto", "not-a-command"],
    }
    for name, argv in cases.items():
        proc = _run(argv, b"")
        assert proc.returncode == 2, (name, proc.returncode, proc.stderr)
        assert b"usage:" in proc.stderr.lower(), (name, proc.stderr)


def test_shims_refuse_an_absent_plugin_root(tmp_path):
    """The shell entry points do not mask a missing host-provided plugin root."""
    for shim in ("_dispatch_shim.sh", "_dispatch_configchange_shim.sh"):
        proc = _run([str(REPO / "makoto" / shim)], b"{}", env={
            "MAKOTO_STATE_DIR": str(tmp_path / shim),
            "CLAUDE_PLUGIN_ROOT": "",
        })
        assert proc.returncode == 2, (shim, proc.returncode, proc.stderr)
        assert b"NOT_EVALUABLE" in proc.stderr
