from __future__ import annotations
import os
import tempfile
from pathlib import Path
from makoto.stopchecks._types import StopCheck
from makoto.stopchecks.liveness import analyze_file
from makoto.schema import Finding


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
    contamination vector) is skipped. This realizes "a block counts only when opened AND closed" at
    the unit-closure layer: the analyzer's detection logic is untouched, the firing scope narrows to
    closed work. Suppression requires a known cwd AND a scratch root -- never a blanket skip -- so an
    unknown working dir keeps the gate's full teeth and a real (non-temp) file always fires."""
    if not cwd:
        return False                                         # working dir unknown -> never suppress (FN-safe)
    rp = os.path.realpath(str(p))
    if _under(rp, os.path.realpath(str(cwd))):
        return False                                         # inside the working dir -> in scope
    return any(_under(rp, r) for r in _SCRATCH_ROOTS)        # outside cwd AND in a scratch root -> stray scratch


def _read(ctx, p):
    fn = getattr(ctx, "fs_read", None)
    return fn(p) if callable(fn) else Path(p).read_text(encoding="utf-8")


def _run(ctx) -> list:
    out = []
    cwd = getattr(ctx, "cwd", None)
    for p in getattr(ctx, "touched", ()):
        if not str(p).endswith(".py"):
            continue
        if _is_scratch(p, cwd):
            continue                                         # stray scratch outside the working project -> not a closed unit
        try:
            src = _read(ctx, p)
        except OSError:
            continue
        if not isinstance(src, str):
            continue                                         # fs_read miss (None) -> skip, never crash
        for f in analyze_file(src, str(p)):
            out.append(Finding(
                pattern_id="gate.liveness",
                file=str(p),
                line=f["line"],
                level="error",                               # a BLOCKING finding
                message=(f"illusory code: {f['func']} line {f['line']} is pure and never reaches I/O. "
                         f"Make it material (use its result / give it an effect) or remove it before this "
                         f"is complete; annotate `# makoto-allow: <reason>` only if it is intentional."),
            ))
    return out


# A Stop gate (fires on the Stop hook, like every gate). Its `fn` is the AST analyzer rather than a
# claim-vs-ledger predicate, so its teeth are audited BEHAVIORALLY (the soundness/FP suite +
# test_dispatch_liveness_gate_blocks), not by falsify's single-fn mutation harness — see
# scripts/falsify._BEHAVIORAL_TEETH. `run` returns list[Finding] (a closed unit can have many
# illusory statements); run_stop_checks normalizes a list exactly like a single finding.
GATE = StopCheck(id="gate.liveness", fn=analyze_file, run=_run)
