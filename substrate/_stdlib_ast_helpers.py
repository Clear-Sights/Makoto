"""Shared stdlib-only helpers for the detector engines that deliberately isolate themselves from
mutable Makoto substrate (`deadPureStatement.py`, `hollowTest.py`) -- so tampering with shared
plugin logic (substrate.factories, checks._shared, ...) can't silently blind either detector.

This module exists to satisfy that property WITHOUT duplicating the functions below byte-for-byte
across both files (found via AST alpha-equivalence, 2026-07-09): both detectors import ONLY this
module, which itself imports nothing beyond `os`/`tempfile`/`pathlib`/`ast` -- so the
import-graph-isolation property is preserved and enforced (see
tests/test_detector_engines_are_stdlib_isolated.py), not just asserted by a docstring.

Do not add an import of anything outside the stdlib to this file -- doing so would break the one
property it exists to protect for every detector that imports it.
"""
from __future__ import annotations

import ast
import os
import tempfile
from pathlib import Path


def _scratch_roots() -> tuple[str, ...]:
    roots = []
    for d in (tempfile.gettempdir(), "/tmp", "/var/folders", os.path.expanduser("~/.claude")):
        try:
            roots.append(os.path.realpath(d))
        except OSError:
            pass
    return tuple(roots)


_SCRATCH_ROOTS = _scratch_roots()


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _is_scratch(p, cwd) -> bool:
    """A touched .py is out-of-scope scratch iff cwd is KNOWN, the file is NOT inside that working
    dir, AND it lives under a known temp/scratch root. A file under cwd is the closed unit under
    construction (this is how pytest tmp fixtures and real project files appear) and always counts;
    only stray scratch OUTSIDE the working project (e.g. /tmp/mining/*, the live-session
    contamination vector) is skipped. Suppression requires a known cwd AND a scratch root -- never
    a blanket skip -- so an unknown working dir keeps the gate's full teeth and a real (non-temp)
    file always fires."""
    if not cwd:
        return False
    rp = os.path.realpath(str(p))
    if _under(rp, os.path.realpath(str(cwd))):
        return False
    return any(_under(rp, r) for r in _SCRATCH_ROOTS)


def _read(ctx, p):
    fn = getattr(ctx, "fs_read", None)
    return fn(p) if callable(fn) else Path(p).read_text(encoding="utf-8")


def _callee_chain(call: ast.Call) -> str:
    """Dotted callee name of a Call (`self.assertTrue`, `np.testing.assert_allclose`,
    `pytest.raises`). Alpha-equivalent to `substrate/factories.py::callee_chain` -- kept as a
    separate, exempted duplicate (see tests/test_no_alpha_duplicate_functions.py) so this module
    stays stdlib-only/self-contained: importing makoto.substrate.factories would break the
    import-graph isolation the whole module exists to protect."""
    parts: list = []
    f = call.func
    while True:
        if isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        elif isinstance(f, ast.Call):
            f = f.func
        elif isinstance(f, ast.Name):
            parts.append(f.id)
            break
        else:
            break
    return ".".join(reversed(parts))


def iter_touched_python_sources(ctx):
    """Yield (touched_key, source_text) for every in-scope .py file the turn touched -- the
    iteration scaffold deadPureStatement._run and hollowTest._run previously duplicated line for
    line (2026-07-09 dedup; the two bodies differed only INSIDE the loop). Contract preserved
    exactly: a possibly-relative touched key is anchored to the event's OWN cwd, never the
    dispatch process's ambient one (matches _dispatch.py's real fs_read/fs_exists join); stray
    scratch outside the working project is skipped; an OSError or fs_read miss (None) skips the
    file, never crashes the gate."""
    cwd = getattr(ctx, "cwd", None)
    for p in getattr(ctx, "touched", ()):
        if not str(p).endswith(".py"):
            continue
        real_p = p if not cwd or os.path.isabs(str(p)) else os.path.join(cwd, p)
        if _is_scratch(real_p, cwd):
            continue
        try:
            src = _read(ctx, real_p)
        except OSError:
            continue
        if not isinstance(src, str):
            continue
        yield p, src
