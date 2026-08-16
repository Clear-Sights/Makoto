"""gate.undeclared_falsifiable -- declared-falsifiability COMPLETENESS (SPEC-5 Task 2 Step 6).

Distinct from anything Assay does: Assay forces a claim to *be* falsifiable (a predicate that
can concretely fail). This check separately audits that every piece claiming falsifiability in
`checks/` is actually *declared* -- a manifest-vs-reality auditor over the check catalog itself:
does every file in `checks/` register itself where the loader looks (`_loader.load_checks`),
does every ID declared in the catalog's manifest (`_declared.DECLARED_IDS`) have a
corresponding live module, is there an orphan on either side. A flat, enumerable folder needs
this explicit completeness check to catch the same class of drift a folder-per-category split
used to catch for free by eyeball (a moved-and-forgotten file, a registered ID with no module, a
module with no registration).

Same Stop-time, advisory-tier shape as `stopchecks/stopcheck_self_wired.py` (predicate-injection
style: the pure functions below take their inputs as arguments, never reach for global state
directly, so they're exercised with synthetic/tmp_path fixtures in tests without ever mutating
the real live `checks/` package) -- but this check audits the checks/ catalog's own internal
consistency, not whether the faculty is wired into the host at all.

ADVISORY tier only (`level="advisory"`, never `"error"`), per this repo's "advisory over
blocking" standing policy: a catalog-completeness drift is a maintenance signal, not a live
integrity violation of anything the agent claimed this turn, so it must never block a turn.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from makoto.substrate._declared import DECLARED_IDS
from makoto.substrate._loader import Check, scan
from makoto.verdict.posture import ADVISE
from makoto.core.schema import Finding


def orphan_modules(*, package_dir: Optional[Path] = None) -> list:
    """File stems present in checks/ that do NOT produce a `load_checks()`-discoverable CHECK:
    exists on disk, not discoverable/registered. Sorted for determinism."""
    return sorted(stem for stem, chk in scan(package_dir=package_dir).items() if chk is None)


def orphan_ids(*, package_dir: Optional[Path] = None, declared: Optional[dict] = None) -> list:
    """IDs listed in the declared-IDs manifest with no live module backing them: declared, no
    module. `declared` defaults to the real catalog's `_declared.DECLARED_IDS` (test-injectable
    so a test can plant a dangling ID without touching the real manifest). Sorted for
    determinism."""
    reg = DECLARED_IDS if declared is None else declared
    live_ids = {getattr(chk, "id", None) for chk in scan(package_dir=package_dir).values()
                if chk is not None}
    return sorted(pid for pid in reg if pid not in live_ids)


def undeclared_falsifiable_gate(*, package_dir: Optional[Path] = None,
                                 declared: Optional[dict] = None) -> Optional[Finding]:
    """Fires iff the checks/ catalog has an orphan on either side (see `orphan_modules` /
    `orphan_ids`); `None` (no finding) on a fully consistent catalog. Fail-open by
    construction: both halves already fail-open internally (`scan` never raises)."""
    mods = orphan_modules(package_dir=package_dir)
    ids = orphan_ids(package_dir=package_dir, declared=declared)
    if not mods and not ids:
        return None
    parts = []
    if mods:
        parts.append(f"orphan module(s) on disk with no live CHECK registered: {', '.join(mods)}")
    if ids:
        parts.append(f"declared ID(s) in the manifest with no live module backing them: {', '.join(ids)}")
    return Finding(
        pattern_id="gate.undeclared_falsifiable",
        file="makoto/checks/",
        line=0,
        level="advisory",
        message="checks/ catalog completeness drift -- " + "; ".join(parts),
        retry_hint=("Fix the checks/ catalog: give every on-disk module a valid CHECK "
                     "(id/applies_at/posture), and either implement or remove every "
                     "declared-but-missing manifest entry in _declared.py."),
    )


CHECK = Check(
    id="gate.undeclared_falsifiable",
    applies_at="Stop",
    posture=ADVISE,
    run=lambda ctx=None: undeclared_falsifiable_gate(),
)
