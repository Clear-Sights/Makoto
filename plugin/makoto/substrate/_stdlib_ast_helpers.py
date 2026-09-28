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
    if _under(rp.lower(), os.path.realpath(str(cwd)).lower()):
        return False                                         # inside the working dir -> in scope
    # (compared case-folded: ledger keys are folded, so on a case-insensitive disk the folded key
    # names the file but realpath keeps the fold, and `.../T/...` vs `.../t/...` read as outside;
    # folding can only widen scope, never skip a file)
    return any(_under(rp, r) for r in _SCRATCH_ROOTS)        # outside cwd AND in a scratch root -> stray scratch


def on_disk(p: str) -> str:
    """The path as the filesystem spells it. Ledger keys are case-folded for equality
    (`kit.normalize_path`), so a key under `Measure-Zero/` reads as `measure-zero/` and names no
    file on a case-sensitive disk. Each component that does not exist as written is replaced by
    the one directory entry equal to it case-insensitively; none or several leaves `p` as it was."""
    if not p or os.path.exists(p):
        return p
    head, parts = p, []
    while head and not os.path.exists(head):
        head, tail = os.path.split(head)
        if not tail:
            return p
        parts.append(tail)
    for part in reversed(parts):
        exact = os.path.join(head, part)
        if os.path.exists(exact):
            head = exact                                  # spelled as written: never re-guessed
            continue
        try:
            hits = [e for e in os.listdir(head or ".") if e.lower() == part.lower()]
        except OSError:
            return p
        if len(hits) != 1:
            return p
        head = os.path.join(head, hits[0])
    return head


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
        joined = p if os.path.isabs(str(p)) else os.path.join(cwd, p)
        real_p = on_disk(joined)
        if _is_scratch(real_p, cwd):
            continue
        try:
            src = _read(fs_read, real_p)
        except Exception:
            continue
        if not isinstance(src, str):
            continue
        yield (real_p if real_p != joined else p), src
