"""Shared stdlib-only helpers for the detector engines that deliberately isolate themselves from
mutable Makoto substrate (`deadPureStatement.py`, `hollowTest.py`) -- so tampering with shared
plugin logic can't silently blind either detector.

Both detectors import ONLY this module, which itself imports nothing beyond
`os`/`tempfile`/`pathlib`/`ast`, so the import-graph-isolation property is enforced (see
tests/test_detector_engines_are_stdlib_isolated.py), not just asserted by a docstring.

Do not add an import of anything outside the stdlib to this file.
"""
from __future__ import annotations

import ast
import os
import tempfile
from pathlib import Path


def _scratch_roots() -> tuple[str, ...]:
    roots: dict[str, None] = {}                       # insertion-ordered set
    for d in (tempfile.gettempdir(), "/tmp", "/var/folders", os.path.expanduser("~/.claude")):
        try:
            roots[os.path.realpath(d)] = None         # dedupes gettempdir() == /tmp on Linux
        except OSError:
            pass
    return tuple(roots)


_SCRATCH_ROOTS = _scratch_roots()


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _is_scratch(p, cwd) -> bool:
    """A touched .py is out-of-scope scratch iff cwd is KNOWN, the file is NOT inside that working
    dir, AND it lives under a known temp/scratch root. A file under cwd always counts; only stray
    scratch outside the working project is skipped. Suppression requires a known cwd AND a
    scratch root -- never a blanket skip -- so an unknown working dir keeps the gate's full teeth."""
    if not cwd:
        return False                                         # working dir unknown -> never suppress (FN-safe)
    rp = os.path.realpath(str(p))
    if _under(rp, os.path.realpath(str(cwd))):
        return False                                         # inside the working dir -> in scope
    return any(_under(rp, r) for r in _SCRATCH_ROOTS)        # outside cwd AND in a scratch root -> stray scratch


def _read(fs_read, p):
    return fs_read(p) if callable(fs_read) else Path(p).read_text(encoding="utf-8")


def _callee_chain(call: ast.Call) -> str:
    """Dotted callee name of a Call (`self.assertTrue`, `np.testing.assert_allclose`, `pytest.raises`)."""
    parts: list = []
    f = call.func
    while True:
        if isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        elif isinstance(f, ast.Call):
            f = f.func                       # `X().<m>` -> keep walking X
        elif isinstance(f, ast.Name):
            parts.append(f.id)
            break
        else:
            break
    return ".".join(reversed(parts))


def iter_touched_python_sources(touched, cwd, fs_read):
    """Yield (touched_key, source_text) for every in-scope .py file the turn touched -- the
    iteration scaffold deadPureStatement._run and hollowTest._run both share.

    A possibly-relative touched key is anchored to the event's OWN cwd, never the dispatch
    process's ambient one; a relative key with NO known cwd is unanchorable and skipped outright
    (resolving it would cite the touched key with another file's line numbers). Stray scratch
    outside the working project is skipped; ANY per-file read fault or an fs_read miss (None)
    skips THAT file only, never crashes the gate. `touched` is a set; iteration is sorted so
    which file a Finding cites is reproducible across processes."""
    for p in sorted(touched, key=str):
        if not str(p).endswith(".py"):
            continue
        if not cwd and not os.path.isabs(str(p)):
            continue
        real_p = p if os.path.isabs(str(p)) else os.path.join(cwd, p)
        if _is_scratch(real_p, cwd):
            continue
        try:
            src = _read(fs_read, real_p)
        except Exception:
            continue
        if not isinstance(src, str):
            continue
        yield p, src
