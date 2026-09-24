"""makoto.registry — the flat checks/ package's own discovery mechanism.

A check module is any `.py` file directly under `makoto/checks/` whose name does NOT start
with `_` (package plumbing -- `__init__.py`, `_loader.py`, `_primitives.py`, `_declared.py`,
and any future underscore-prefixed helper -- is never a detector module and is skipped by the
scan). A live check module exposes a module-level `CHECK` object with three duck-typed
attributes: `.id` (str), `.applies_at` (one of Pre/Post/Stop/SubagentStop/SessionStart), and
`.posture` (this check's own native outcome tier before the operator's configured MAKOTO_MODE
posture folds over it -- see `makoto.verdict`'s OUTCOME vocabulary). A candidate file that fails
to import, has no `CHECK`, or whose `CHECK` fails this shape check is silently skipped
(fail-open, matching every other loader/gate in this codebase) -- `checks.undeclaredFalsifiable`
is the one check whose job is to surface that skip as a finding instead of silence.

This module is the sole discovery path for both edges; `load_precheck_catalog()` is the Pre-tier
convenience wrapper."""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# The only admissible `applies_at` values -- the five hook edges the posture skeleton
# recognizes.
ALLOWED_EDGES = frozenset({"Pre", "Post", "Stop", "SubagentStop", "SessionStart"})
# The four families of the register: what pays a check's subject. SPEC holds its definition and
# needs no witness; the other three decide through `kit.unwitnessed`, each with its own witness --
# a second reading of the subject (OTHER_POINT), an act and its response (SWITCH), a read of the
# source before the write drawn from it (LINEAGE).
TESTS_SHAPES = frozenset({"SPEC", "OTHER_POINT", "SWITCH", "LINEAGE"})

# The ONLY documented exception to "every Stop-gate finding blocks" (DESIGN DECISION 6):
# gate.self_wired ships at level="advisory" so a partial hook-wiring strip is recorded to the audit
# trail without ever blocking a turn (stopchecks/stopcheck_self_wired.py's own docstring; behavioral
# pin: tests/test_dispatch.py::test_dispatch_self_wired_gate_never_blocks_even_when_it_fires).
# Adding a gate id here must cite its own DESIGN DECISION the same way.
#
# gate.canon_fingerprints_advisory (DESIGN DECISION 26) is the second: most of the ported canon
# session fingerprints rest on a soft/claim atom the gold-oracle finding doc's robust core does
# not name, or are among that doc's explicitly-named WORST DISQUALIFIED fingerprints — the
# total-retention rule keeps them in the catalog, evaluated and recorded, but never blocking. Its
# sibling gate.canon_fingerprints (the robust-core, blocking-capable fingerprints) is
# intentionally NOT here — it always emits level="error" (see canonFingerprints.py).
# gate.unprobed_fanout and gate.unasked_plan are the third and fourth: both are ACT_VS_GUARD
# obligations with a real benign class (a dispatch that IS the exploration; a plan for a request
# that carried no ambiguity) and no corpus-measured FP rate yet. Promoting either to BLOCK needs
# that measurement, not a preference. Each module's docstring says so.
_ADVISORY_ALLOWLIST = frozenset({"gate.self_wired", "gate.canon_fingerprints_advisory",
                                  "gate.relative_path_citation", "gate.plan_item_drift",
                                  "gate.unprobed_fanout", "gate.unasked_plan",
                                  # same reasoning: each has a named benign class in its own
                                  # module docstring and no corpus-measured FP rate yet.
                                  "gate.unread_structure",
                                  "gate.unwitnessed_verifier",
                                  "gate.unknown_ref_switch",
                                  "gate.unobserved_destruction",
                                  "gate.relaunched_unchanged",
                                  # a deliberately permanent waiver is a real and common thing
                                  # and looks identical to an oversight.
                                  "gate.undischarged_waiver",
                                  # the benign case (the runner's own summary pasted, names
                                  # visible in it) looks identical.
                                  "gate.unnamed_failure",
                                  # DOCUMENTING a command's output in a session that never
                                  # ran it looks identical.
                                  "gate.report_before_run",
                                  # an unreachable new unit and a premature abstraction look
                                  # the same from the record.
                                  "gate.unclaimed_unit",
                                  # a check-id list this architecture keeps in three homes, and
                                  # a house convention wider than four lines, are both measured
                                  # benign classes that look identical from the record.
                                  "gate.pasted_fix",
                                  })

# THE CHECK-POSTURE VOCABULARY, closed. Three different things in this package are called
# "posture" and they are three different vocabularies: a CHECK's native tier is `BLOCK`/`ADVISE`
# (here); `makoto.verdict`'s OUTCOME vocabulary is `block`/`advise` lower-case; and
# `verdict._POSTURES` is the operator's configured mode, `loose`/`strict`/`ask`/`silent`.
# `_valid_check` used to require only that `posture` be truthy, so any spelling loaded -- and two
# checks shipped their native tier spelled in the OUTCOME vocabulary's case. Nothing noticed,
# because the one consumer that publishes a blocking count never read posture at all. With the
# set closed, a fourth spelling cannot be loaded rather than being caught later by a reader.
POSTURE_BLOCK = "BLOCK"
POSTURE_ADVISE = "ADVISE"
ALLOWED_POSTURES = frozenset({POSTURE_BLOCK, POSTURE_ADVISE})


def blocking_eligible(check) -> bool:
    """Which end-of-turn gates the catalog counts as blocking. ONE owner OF THAT COUNT,
    called by every consumer of it -- not the one owner of the word: a pre-check denies
    without being Stop-edge, and `_canonAtoms.BLOCK_IDS` counts patterns rather than checks.
    README lists all of them.

    The Check docstring below has always defined this as BOTH signals: `may_block is True`
    AND `posture == BLOCK`. `tools/render_checks.py` implemented a different rule -- Stop
    edge, `may_block`, and absence from `_ADVISORY_ALLOWLIST` -- and never consulted posture
    at all. The two agree on today's catalog only because the allowlist happens to name
    exactly the four checks whose posture is ADVISE. Set a gate's posture to ADVISE without
    editing the allowlist and the README goes on calling it blocking, because the sentence
    that defines the word and the code that publishes the count were different owners.
    """
    return (getattr(check, "applies_at", None) == "Stop"
            and bool(getattr(check, "may_block", False))
            and getattr(check, "posture", None) == POSTURE_BLOCK)


_PACKAGE_DIR = Path(__file__).parent / "checks"


@dataclass(frozen=True)
class Check:
    """A convenience shape a check module MAY use for its `CHECK` export -- not required, the
    loader only duck-types `.id` / `.applies_at` / `.posture`, so a module exporting its own
    richer dataclass is equally discoverable.

    `may_block`: a Stop-edge check is blocking-eligible only when BOTH `may_block is True` AND
    `posture == BLOCK` -- two independent signals, not one. A Pre-tier CHECK leaves it False.


    `keywords`/`retry_hint`/`description`/`predicate_module` are Pre-tier fields; Stop-tier checks
    leave their safe empty defaults.

    `eats` is the check's exact declared input signature. Stop checks name GateContext fields or
    derived properties; Pre checks use the flat predicate vocabulary current_event/history/
    pattern/conn. tests/test_check_law_eats.py derives the reachable reads and rejects either an
    undeclared read or a dead declaration.

    `tests` declares the check's result/evidence shape (one of `TESTS_SHAPES`). The sibling
    tests/test_check_law_tests.py rejects both an undeclared shape and a declaration whose
    module/factory does not use that shape's required evidence primitive. Genuine one-offs keep
    the empty default only when their id and reason are registered explicitly in that law.

    `layer` is "object" or "meta" (default "object"); "meta" means the check can trigger only on
    tampering with Makoto's own audit/enforcement machinery. A meta BLOCK cannot soften below ASK
    under LOOSE/SILENT."""
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
        and getattr(chk, "posture", None) in ALLOWED_POSTURES
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


def _iter_modules(directory: Path):
    """`(file_stem, imported-module-or-None)` for every candidate file in `directory`, in
    file-stem order -- the one candidate walk `scan()` and `discover()` share. A `None` module
    means the file failed to import; that is recorded, not raised. Every family module carries
    rows at both edges, so there is no edge to skip a file by."""
    for path in _candidate_files(directory):
        try:
            mod = _load_module(path, directory)
        except Exception:
            mod = None
        yield path.stem, mod


def scan(*, package_dir: Optional[Path] = None) -> dict:
    """`{file_stem: CHECK-or-None}` for every candidate file in `package_dir` (defaults to the
    real `checks/` package). `None` means the file failed to produce a valid,
    loader-discoverable `CHECK` -- an orphan module, in `gate.undeclared_falsifiable`'s
    vocabulary. Never raises: an import failure is recorded as `None`, not propagated."""
    directory = package_dir or _PACKAGE_DIR
    return {stem: _primary_check(mod) for stem, mod in _iter_modules(directory)}


def discover(*, package_dir: Optional[Path] = None) -> list:
    """Every valid check found directly in `package_dir` (defaults to the real `checks/`
    package), in file-stem order: each module's `CHECK` and then its `EXTRA_CHECKS` -- a family
    module exports its rows as `CHECK, *EXTRA_CHECKS`. Each is validated (`_valid_check`) and a
    malformed one is skipped, not fatal."""
    directory = package_dir or _PACKAGE_DIR
    primary, extra = [], []
    for _stem, mod in _iter_modules(directory):
        chk = _primary_check(mod)
        if chk is not None:
            primary.append(chk)
        extra.extend(x for x in (getattr(mod, "EXTRA_CHECKS", None) or []) if _valid_check(x))
    # Identity dedupe: a module listing the SAME object as both `CHECK` and an `EXTRA_CHECKS`
    # entry (tests/test_gate_shape.py accepts either placement, so nothing upstream rejects
    # listing both) must not get that one check evaluated twice in a single verdict -- the
    # same finding would be emitted twice for one event. Distinct objects sharing an id (the
    # documented dual-surface shape) are untouched.
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
    """
    found = discover(package_dir=package_dir)
    if edge is not None:
        found = [c for c in found if c.applies_at == edge]
    return found


def load_precheck_catalog(*, package_dir: Optional[Path] = None) -> list:
    """Every live Pre-tier `CHECK` with a `predicate_module` set -- the keyword-prefiltered
    detector catalog `dispatch._run_predicates` (and `install.py`/`__main__.py`'s catalog
    inspection commands) consume. The BLOCK-only invariant is pinned by
    `tests/test_pre_tier_block_invariant.py`"""
    return [c for c in load_checks(edge="Pre", package_dir=package_dir) if c.predicate_module]
