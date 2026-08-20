"""Scope-pinned tracked-file lister for makoto's self-scan tests (the git-ls-files cwd hazard fix).

The monorepo has no per-faculty .git, so a bare `git ls-files "*.py"` resolves against whatever
enclosing repo the CURRENT working directory sits in and lists files relative to cwd — from the
repo root it sweeps every faculty's *.py (foils included), from makoto/ only makoto's. That is a
silent mis-scope (wrong corpus, not a crash). Pinning scope with `git -C <root>` makes the corpus a
function of the explicit `root` argument alone, never the caller's cwd."""
from __future__ import annotations

import subprocess
from pathlib import Path

MAKOTO_ROOT = Path(__file__).resolve().parent.parent   # makoto/tests/ -> makoto/


def tracked_py_files(root: str | Path = MAKOTO_ROOT, *, exclude_tests: bool = True) -> list[str]:
    """Tracked `*.py` files UNDER `root`, listed cwd-independently (`git -C <root>`), returned
    root-relative (git ls-files' own output form). With `exclude_tests` (default), every path in a
    directory named `tests` is dropped — the same non-test corpus the liveness/hollow-test FP
    falsifiers measure. Listing failures are loud: an unknown corpus must never measure as zero
    fires."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.py"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError(f"could not list tracked Python files under {root}")
    files = [f for f in out.split("\0") if f]
    if exclude_tests:
        files = [f for f in files if "tests" not in Path(f).parts]
    if not files:
        raise RuntimeError(f"tracked Python corpus under {root} is empty")
    return files


__all__ = ["tracked_py_files", "MAKOTO_ROOT"]
