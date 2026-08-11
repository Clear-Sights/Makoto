"""Regression coverage for the repository's POSIX-shell test runner."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "tests" / "bash" / "run_all.sh"


def test_bash_runner_executes_the_shipped_smoke_test():
    proc = subprocess.run(["sh", str(RUNNER)], cwd=REPO_ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "=== smoke_test.sh ===" in proc.stdout
    assert "Smoke complete." in proc.stdout
    assert "All bash tests passed." in proc.stdout


def test_bash_runner_fails_loudly_when_no_tests_match(tmp_path):
    runner = tmp_path / "run_all.sh"
    shutil.copy2(RUNNER, runner)
    proc = subprocess.run(["sh", str(runner)], text=True, capture_output=True)
    assert proc.returncode == 1
    assert "no bash tests matched" in (proc.stdout + proc.stderr).lower()
