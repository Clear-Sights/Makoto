"""makoto.substrate._loader — the flat checks/ package's own discovery mechanism (SPEC-5 Task 2).

A check module is any `.py` file directly under `makoto/checks/` whose name does NOT start
with `_` (package plumbing -- `__init__.py`, `_loader.py`, `_primitives.py`, `_declared.py`,
and any future underscore-prefixed helper -- is never a detector module and is skipped by the
scan). A live check module exposes a module-level `CHECK` object with three duck-typed
attributes: `.id` (str), `.applies_at` (one of Pre/Post/Stop/SubagentStop/SessionStart), and
`.posture` (this check's own native outcome tier before the operator's configured MAKOTO_MODE
posture folds over it -- see `makoto.verdict.posture`'s OUTCOME vocabulary). A candidate file that fails
to import, has no `CHECK`, or whose `CHECK` fails this shape check is silently skipped
(fail-open, matching every other loader/gate in this codebase) -- `checks.undeclaredFalsifiable`
(SPEC-5 Task 2 Step 6) is the one check whose job is to surface that skip as a finding instead
of silence.

This coexists with, and does not yet supersede, `schema.load_prechecks`. Stop-edge discovery
itself WAS superseded (SPEC-C item 2, 2026-07-07): `_dispatch.py`'s Stop-finding loop and its
`_blocking_gate_ids()` both run on `load_checks(edge="Stop")` now, not the former
`stopchecks.load_stopchecks`/`GATE`-export mechanism kept below only for the tests that still
assert against it directly (see `load_stopchecks`'s own docstring).
"""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

# The only admissible `applies_at` values -- the five hook edges Task 1's posture skeleton
# recognizes.
ALLOWED_EDGES = frozenset({"Pre", "Post", "Stop", "SubagentStop", "SessionStart"})

_PACKAGE_DIR = Path(__file__).parent.parent / "checks"


@dataclass(frozen=True)
class Check:
    """A convenience shape a check module MAY use for its `CHECK` export -- not required, the
    loader only duck-types `.id` / `.applies_at` / `.posture`, so a module exporting its own
    richer dataclass (e.g. one shaped like `stopchecks._types.StopCheck`) is equally
    discoverable.

    SPEC-C item 2 (Pre-tier cutover, 2026-07-07): `keywords`/`retry_hint`/`description`/
    `predicate_module` are additive fields, consumed only by `schema.load_prechecks()`'s
    loader-backed default path and by the Pre-tier predicates themselves (which read
    `pattern.retry_hint`/`pattern.description` directly to build their Finding -- see
    `phantomCitation.py`/`forbiddenLocation.py`). A Stop-tier CHECK never sets them and reads
    them back as their safe empty defaults. `predicate_module` is conventionally set to the
    module's own `__name__` at CHECK-construction time (self-referential, never a
    hand-typed/stale dotted string)."""
    id: str
    applies_at: str
    posture: str
    run: Optional[Callable] = None
    keywords: tuple = ()
    retry_hint: str = ""
    description: str = ""
    predicate_module: str = ""


def _candidate_files(directory: Path) -> list:
    """Every non-underscore-prefixed `.py` file directly in `directory`, sorted for determinism."""
    return sorted(p for p in directory.glob("*.py") if not p.name.startswith("_"))


def _load_module(path: Path, directory: Path):
    """Import `path`. Scanning the real package (`directory == _PACKAGE_DIR`) imports it
    properly as `makoto.checks.<name>` (normal caching, normal tracebacks, normal
    `sys.modules` identity). Scanning an isolated directory (tests only) imports it by file
    path under a private name so a tmp_path scan never pollutes `sys.modules` for the real
    package or collides with another tmp_path scan's same-named file."""
    name = path.stem
    if directory == _PACKAGE_DIR:
        return importlib.import_module(f"makoto.checks.{name}")
    spec = importlib.util.spec_from_file_location(f"_makoto_checks_scan__{id(directory)}__{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _valid_check(chk) -> bool:
    return (
        bool(getattr(chk, "id", None))
        and getattr(chk, "applies_at", None) in ALLOWED_EDGES
        and bool(getattr(chk, "posture", None))
    )


def scan(*, package_dir: Optional[Path] = None) -> dict:
    """`{file_stem: CHECK-or-None}` for every candidate file in `package_dir` (defaults to the
    real `checks/` package). `None` means the file failed to produce a valid,
    loader-discoverable `CHECK` -- an orphan module, in `checks.undeclaredFalsifiable`'s
    vocabulary. Never raises: an import failure is recorded as `None`, not propagated."""
    directory = package_dir or _PACKAGE_DIR
    out = {}
    for path in _candidate_files(directory):
        try:
            mod = _load_module(path, directory)
            chk = getattr(mod, "CHECK", None)
        except Exception:
            chk = None
        out[path.stem] = chk if (chk is not None and _valid_check(chk)) else None
    return out


def discover(*, package_dir: Optional[Path] = None) -> list:
    """Every valid `CHECK` found directly in `package_dir` (defaults to the real `checks/`
    package), in file-stem order. A module MAY additionally export `EXTRA_CHECKS: list` for a
    second (or more) firing surface sharing the same file/id at a DIFFERENT `applies_at` edge --
    e.g. `contractOrder.py`'s Stop-side GATE, which shares the id `gate.contract_order` with
    that same module's Pre-side CHECK/predicate (SPEC-C item 2, FABLE DECISION 2026-07-07: the
    only module in the catalog with two firing surfaces under one id; this is a small, explicit
    generalization of the loader's contract rather than a special-cased carve-out for it). Each
    `EXTRA_CHECKS` entry is validated the same way as a primary CHECK (`_valid_check`) and
    silently skipped (not fatal) if malformed -- consistent with every other loader failure mode
    in this module."""
    directory = package_dir or _PACKAGE_DIR
    out = [chk for chk in scan(package_dir=directory).values() if chk is not None]
    for path in _candidate_files(directory):
        try:
            mod = _load_module(path, directory)
        except Exception:
            continue
        for extra in getattr(mod, "EXTRA_CHECKS", None) or []:
            if _valid_check(extra):
                out.append(extra)
    return out


def load_checks(edge: Optional[str] = None, *, package_dir: Optional[Path] = None) -> list:
    """The flat checks/ package's discovery entry point: every live `CHECK`, optionally
    filtered to one `applies_at` edge ("Pre"/"Post"/"Stop"/"SubagentStop"/"SessionStart");
    omit `edge` for every discovered check regardless of edge. `package_dir` is test-only (see
    `scan`) -- production callers always get the real package.
    """
    found = discover(package_dir=package_dir)
    if edge is not None:
        found = [c for c in found if c.applies_at == edge]
    return found


@lru_cache(maxsize=1)
def load_stopchecks() -> list:
    """Every module directly under `makoto/checks/` that exports a `GATE` (a `StopCheck`,
    distinct from that same module's `CHECK` used by `load_checks`). Memoized so a repeat call
    never re-scans the filesystem.

    Relocated here (2026-07-09) from the former `stopchecks/__init__.py` compat shim, which has
    been removed entirely -- no callers should still import it from `makoto.stopchecks`; that
    package no longer exists.

    NOT called by production anymore in this repo: SPEC-C item 2 (2026-07-07) moved
    `_dispatch.py`'s Stop-finding loop and `_blocking_gate_ids()` onto `load_checks(edge="Stop")`
    before this relocation happened, so `GATE`/`load_stopchecks()` are vestigial here -- kept
    only because a set of tests still assert Stop-gate properties (discovery, count, memoization,
    firing behavior) directly against this mechanism. Whether to retire `GATE` from the 14 check
    modules that still export it and rewrite those tests onto `load_checks(edge="Stop")` instead
    is a separate, larger decision this relocation does not make (dev's own `_dispatch.py` still
    calls `load_stopchecks()` live, so retiring `GATE` here would diverge the two repos' check
    module contracts)."""
    out = []
    for path in _candidate_files(_PACKAGE_DIR):
        mod = importlib.import_module(f"makoto.checks.{path.stem}")
        g = getattr(mod, "GATE", None)
        if g is not None:
            out.append(g)
    return sorted(out, key=lambda g: g.id)
