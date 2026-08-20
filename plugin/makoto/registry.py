"""makoto.registry — the flat checks/ package's own discovery mechanism (SPEC-5 Task 2).

A check module is any `.py` file directly under `makoto/checks/` whose name does NOT start
with `_` (package plumbing -- `__init__.py`, `_loader.py`, `_primitives.py`, `_declared.py`,
and any future underscore-prefixed helper -- is never a detector module and is skipped by the
scan). A live check module exposes a module-level `CHECK` object with three duck-typed
attributes: `.id` (str), `.applies_at` (one of Pre/Post/Stop/SubagentStop/SessionStart), and
`.posture` (this check's own native outcome tier before the operator's configured MAKOTO_MODE
posture folds over it -- see `makoto.verdict`'s OUTCOME vocabulary). A candidate file that fails
to import, has no `CHECK`, or whose `CHECK` fails this shape check is silently skipped
(fail-open, matching every other loader/gate in this codebase) -- `checks.undeclaredFalsifiable`
(SPEC-5 Task 2 Step 6) is the one check whose job is to surface that skip as a finding instead
of silence.

This module is the sole discovery path for both edges; `load_precheck_catalog()` is the Pre-tier
convenience wrapper. See docs/adr/0001-unified-check-discovery.md for the migration history."""
from __future__ import annotations

import importlib
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# The only admissible `applies_at` values -- the five hook edges Task 1's posture skeleton
# recognizes.
ALLOWED_EDGES = frozenset({"Pre", "Post", "Stop", "SubagentStop", "SessionStart"})
TESTS_SHAPES = frozenset({
    "PATTERN_MATCH", "CLAIM_VS_HISTORY", "CLAIM_VS_LEDGER", "LIVE_QUERY", "TESTRUN_DELTA",
})

_PACKAGE_DIR = Path(__file__).parent / "checks"


@dataclass(frozen=True)
class Check:
    """A convenience shape a check module MAY use for its `CHECK` export -- not required, the
    loader only duck-types `.id` / `.applies_at` / `.posture`, so a module exporting its own
    richer dataclass is equally discoverable.

    `may_block`: a Stop-edge check is blocking-eligible only when BOTH `may_block is True` AND
    `posture == BLOCK` -- two independent signals, not one. A Pre-tier CHECK leaves it False.
    See docs/adr/0002-may-block-field.md for the migration history.

    `keywords`/`retry_hint`/`description`/`predicate_module` are Pre-tier fields; Stop-tier checks
    leave their safe empty defaults. See docs/adr/0003-pre-tier-check-fields.md for history.

    `eats` is the check's exact declared input signature. Stop checks name GateContext fields or
    derived properties; Pre checks use the flat predicate vocabulary current_event/history/
    pattern/conn. tests/test_check_law_eats.py derives the reachable reads and rejects either an
    undeclared read or a dead declaration. See docs/adr/0020-check-eats-law.md for history.

    `tests` declares the check's result/evidence shape (one of `TESTS_SHAPES`). The sibling
    tests/test_check_law_tests.py rejects both an undeclared shape and a declaration whose
    module/factory does not use that shape's required evidence primitive. Genuine one-offs keep
    the empty default only when their id and reason are registered explicitly in that law. See
    docs/adr/0021-check-tests-result-shape-law.md for history.

    `layer` is "object" or "meta" (default "object"); "meta" means the check can trigger only on
    tampering with Makoto's own audit/enforcement machinery. A meta BLOCK cannot soften below ASK
    under LOOSE/SILENT. See docs/adr/0004-check-layer-field.md for the decision history."""
    id: str
    applies_at: str
    posture: str
    run: Optional[Callable] = None
    may_block: bool = False
    keywords: tuple = ()
    retry_hint: str = ""
    description: str = ""
    predicate_module: str = ""
    layer: str = "object"
    eats: frozenset[str] = frozenset()
    tests: str = ""


def _candidate_files(directory: Path) -> list[Path]:
    """Every non-underscore-prefixed `.py` file directly in `directory`, sorted for determinism."""
    return sorted(p for p in directory.glob("*.py") if not p.name.startswith("_"))


_APPLIES_AT_RE = re.compile(r'applies_at\s*=\s*["\']([^"\']+)["\']')


def _candidate_edges(path: Path) -> frozenset[str]:
    """Every `applies_at` edge value that appears as a string literal in `path`'s source text --
    read as plain text, WITHOUT importing the module. Used only as a cheap pre-filter so
    `scan()`/`discover()` can skip importing a file that provably cannot contribute to a
    requested `edge`: a module's CHECK (and any EXTRA_CHECKS, e.g. `contractOrder.py`'s dual
    Pre+Stop surface) always spells its `applies_at` as a literal string at the call site --
    verified repo-wide, see this module's own docstring update -- so grepping the source text
    for that pattern yields the exact same edge-set `_valid_check` would see after a real
    import, just without paying the import cost.

    Deliberately conservative in the only direction that matters: if the file can't be read, or
    no `applies_at=...` literal is found at all (e.g. a future check built `applies_at` from a
    variable instead of a literal), this returns "could be any edge" rather than guessing wrong
    -- so the pre-filter can only ever cause an extra, unnecessary import of an irrelevant
    module, never a wrongly-skipped import of a relevant one. `scan()`/`discover()`'s actual
    output (which files' CHECK objects show up) is unchanged by this function's existence
    either way; it only changes how many modules get imported to compute that output."""
    try:
        text = path.read_text()
    except OSError:
        return ALLOWED_EDGES
    edges = frozenset(_APPLIES_AT_RE.findall(text))
    return edges if edges else ALLOWED_EDGES


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


def _primary_check(mod):
    """`mod`'s valid, loader-discoverable `CHECK`, or `None` -- `None` covering all three
    non-fatal ways a candidate file can fail to contribute one: the module never imported
    (`mod is None`), it exports no `CHECK`, or its `CHECK` fails `_valid_check`."""
    try:
        chk = getattr(mod, "CHECK", None)
    except Exception:
        chk = None
    return chk if (chk is not None and _valid_check(chk)) else None


def _iter_modules(directory: Path, edge: Optional[str]):
    """`(file_stem, imported-module-or-None)` for every candidate file in `directory`, in
    file-stem order -- the one candidate walk `scan()` and `discover()` share, so each file is
    globbed, edge-pre-filtered (one `read_text`) and imported exactly once per call rather than
    twice. A `None` module means the file was skipped by the `edge` pre-filter (see
    `_candidate_edges`) or failed to import; neither is fatal, both are recorded, not raised."""
    for path in _candidate_files(directory):
        if edge is not None and edge not in _candidate_edges(path):
            yield path.stem, None
            continue
        try:
            mod = _load_module(path, directory)
        except Exception:
            mod = None
        yield path.stem, mod


def scan(*, package_dir: Optional[Path] = None, edge: Optional[str] = None) -> dict:
    """`{file_stem: CHECK-or-None}` for every candidate file in `package_dir` (defaults to the
    real `checks/` package). `None` means the file failed to produce a valid,
    loader-discoverable `CHECK` -- an orphan module, in `checks.undeclaredFalsifiable`'s
    vocabulary. Never raises: an import failure is recorded as `None`, not propagated.

    `edge`, when given, is a pure import-cost optimization (see `_candidate_edges`): a file
    whose source text provably cannot produce a CHECK at `edge` is recorded as `None` WITHOUT
    being imported at all, instead of being imported just to discover its `applies_at` doesn't
    match. Note what that means for this dict specifically: a stem the pre-filter skipped maps
    to `None` even though an unfiltered `scan()` would have mapped it to a perfectly valid
    `CHECK` at another edge -- `None` here is "produced no CHECK at `edge`", NOT "orphan
    module". A caller that reads `None` as "orphan" (`checks.undeclaredFalsifiable`) must
    therefore call `scan()` with no `edge`, as it does. `discover()`/`load_checks()`, which
    drop `None`s and re-filter by `applies_at` anyway, are unaffected."""
    directory = package_dir or _PACKAGE_DIR
    return {stem: _primary_check(mod) for stem, mod in _iter_modules(directory, edge)}


def discover(*, package_dir: Optional[Path] = None, edge: Optional[str] = None) -> list:
    """Every valid `CHECK` found directly in `package_dir` (defaults to the real `checks/`
    package), in file-stem order. A module MAY additionally export `EXTRA_CHECKS: list` for a
    second (or more) firing surface sharing the same file/id at a DIFFERENT `applies_at` edge --
    `contractOrder.py`'s Stop-side surface, which shares the id "gate.contract_order" with that
    same module's Pre-side CHECK/predicate, is the only module in the catalog with two firing
    surfaces under one id (ported from public Clear-Sights/Makoto's identical mechanism, SPEC-C
    item 2). Each `EXTRA_CHECKS` entry is validated the same way as a primary CHECK
    (`_valid_check`) and silently skipped (not fatal) if malformed -- consistent with every other
    loader failure mode in this module.

    `edge`, when given, is applied by the shared candidate walk (`_iter_modules`) so a file whose
    source text cannot possibly contain an `applies_at` match (in its `CHECK` OR its
    `EXTRA_CHECKS`, since `_candidate_edges` greps the whole file) is never imported at all --
    the import-avoidance this whole parameter exists for. It is a pre-filter only: the final
    per-`applies_at` filtering of the returned list still happens in `load_checks`, unchanged."""
    directory = package_dir or _PACKAGE_DIR
    primary, extra = [], []
    for _stem, mod in _iter_modules(directory, edge):
        chk = _primary_check(mod)
        if chk is not None:
            primary.append(chk)
        extra.extend(x for x in (getattr(mod, "EXTRA_CHECKS", None) or []) if _valid_check(x))
    # Identity dedupe: a module listing the SAME object as both `CHECK` and an `EXTRA_CHECKS`
    # entry (tests/test_gate_shape.py accepts either placement, so nothing upstream rejects
    # listing both) must not get that one check evaluated twice in a single verdict -- the
    # same finding would be emitted twice for one event. Distinct objects sharing an id (the
    # documented dual-surface shape, e.g. contractOrder.py) are untouched.
    out, seen = [], set()
    for chk in primary + extra:
        if id(chk) in seen:
            continue
        seen.add(id(chk))
        out.append(chk)
    return out


def load_checks(edge: Optional[str] = None, *, package_dir: Optional[Path] = None) -> list:
    """The flat checks/ package's discovery entry point: every live `CHECK`, optionally
    filtered to one `applies_at` edge ("Pre"/"Post"/"Stop"/"SubagentStop"/"SessionStart");
    omit `edge` for every discovered check regardless of edge. `package_dir` is test-only (see
    `scan`) -- production callers always get the real package.

    When `edge` is given it is also passed down to `discover()`/`scan()` as an import-cost
    pre-filter (see `_candidate_edges`): a check module whose source text cannot possibly
    produce a CHECK at this edge is never imported in the first place, instead of being
    imported and then filtered out below. The filter below is still the source of truth for
    correctness -- the pre-filter can only skip imports it has proven are irrelevant, never
    change the resulting list.
    """
    found = discover(package_dir=package_dir, edge=edge)
    if edge is not None:
        found = [c for c in found if c.applies_at == edge]
    return found


def load_precheck_catalog(*, package_dir: Optional[Path] = None) -> list:
    """Every live Pre-tier `CHECK` with a `predicate_module` set -- the keyword-prefiltered
    detector catalog `dispatch._run_predicates` (and `install.py`/`__main__.py`'s catalog
    inspection commands) consume. The BLOCK-only invariant is pinned by
    `tests/test_pre_tier_block_invariant.py`; see docs/adr/0001-unified-check-discovery.md for
    the migration history."""
    return [c for c in load_checks(edge="Pre", package_dir=package_dir) if c.predicate_module]
