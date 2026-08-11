"""gate.catalog_completeness -- structural completeness of the flat checks catalog.

This check audits two observable catalog invariants: every candidate module imports with a valid
``CHECK`` export, and every ID in ``_declared.DECLARED_IDS`` has a live loader-discovered check.
It deliberately makes no claim that a registered check's behavior is itself falsifiable; that is
a separate semantic audit and cannot be inferred from registration.

The gate is Stop-time and advisory-only. Its pure functions accept isolated package directories
and manifests so both orphan directions can be planted without mutating the live catalog.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from makoto.substrate._declared import DECLARED_IDS
from makoto.substrate._loader import Check, discover, scan
from makoto.verdict.posture import ADVISE
from makoto.core.schema import Finding


def orphan_modules(*, package_dir: Optional[Path] = None) -> list:
    """Candidate file stems that do not produce a loader-discoverable ``CHECK``."""
    return sorted(stem for stem, chk in scan(package_dir=package_dir).items() if chk is None)


def orphan_ids(*, package_dir: Optional[Path] = None, declared: Optional[dict] = None) -> list:
    """Declared IDs with no live check backing them, sorted for determinism."""
    reg = DECLARED_IDS if declared is None else declared
    live_ids = {chk.id for chk in discover(package_dir=package_dir)}
    return sorted(pid for pid in reg if pid not in live_ids)


def catalog_completeness_gate(*, package_dir: Optional[Path] = None,
                              declared: Optional[dict] = None) -> Optional[Finding]:
    """Fire iff a candidate module or declared manifest ID is orphaned."""
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
        pattern_id="gate.catalog_completeness",
        file="makoto/checks/",
        line=0,
        level="advisory",
        message="checks/ catalog completeness drift -- " + "; ".join(parts),
        retry_hint=("Fix the checks/ catalog: give every on-disk module a valid CHECK "
                    "(id/applies_at/posture), and either implement or remove every "
                    "declared-but-missing manifest entry in _declared.py."),
    )


CHECK = Check(
    id="gate.catalog_completeness",
    applies_at="Stop",
    posture=ADVISE,
    run=lambda ctx=None: catalog_completeness_gate(),
)
