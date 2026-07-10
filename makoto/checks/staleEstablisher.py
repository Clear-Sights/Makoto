"""makoto.checks.staleEstablisher -- the ground-truth staleness detector (OPT-IN, ADVISORY
tier, NEVER BLOCK). Ported BY SHAPE (rule 5) from `assay/assay/patterns/stale_establisher.py`,
re-homed onto Makoto's own `checks._planNode.Plan`.

Fires when a plan node's establisher is recorded DONE but the artifact it named no longer
exists on disk -- the one gap `checks._planNode.Plan`'s pure name->status scan cannot see,
because a node's `status` is a claim about history, never a live filesystem read. This is the
ONE deliberate, explicitly opt-in departure from every other check's content-blind,
filesystem-blind design (an `os.path.exists` call). DETECTIVE tier: a fired verdict is an
ADVISORY, never a deny -- escalating this to a blocking tier is a product decision left to the
caller, not made here.

WIRING (deliberately NOT via `substrate._loader.load_stopchecks`'s GATE discovery): every id that
mechanism discovers auto-BLOCKS by construction ("discovered<=>live<=>blocking -- no shadow
tier", see `checks/_shared.py`) -- exactly the tier this check must never enter. Instead,
`makoto/_dispatch.py`'s `run_stop_checks` calls `check(ctx.plan)` directly and appends its
Finding to the audited-but-never-blocking list (its `pattern_id` never enters
`_blocking_gate_ids()`, so it is STRUCTURALLY incapable of blocking, not just labeled advisory).
This module still exports a `CHECK` (posture=ADVISE) purely for `checks._loader`'s /
`checks.undeclaredFalsifiable`'s completeness discovery -- it is NOT a `GATE` and is never
scanned by `load_stopchecks()`'s blocking-id derivation, so it carries none of that
mechanism's L2-import firewall either.

Reads: the declared Plan (never mutated) and `os.path.exists` on each DONE node's `where`.
Never reads file CONTENT -- existence only, so it stays content-blind even though it is no
longer ledger-blind.
"""
from __future__ import annotations

import os
from typing import Optional

from makoto.substrate._loader import Check
from makoto.substrate._planNode import DONE, Plan
from makoto.verdict.posture import ADVISE
from makoto.core.schema import Finding


def check(plan: Optional[Plan]) -> Optional[Finding]:
    """Fire iff a DONE node's `where` is missing from disk AND a later node shares its
    passthrough (a real dependent whose gap-check would wrongly read as satisfied) -- else
    `None`. `plan=None` (no declared plan) is inert.

    Walks the plan in declared order; for each DONE node, checks whether any LATER node shares
    its passthrough (per the same recurrence rule `checks._planNode` reads) and, only then,
    whether the establisher's `where` still exists on disk (the expensive/impure check runs
    last, only when a dependent makes it matter). The first such contradiction fires; a plan
    with none is an affirmative clean pass (`None`)."""
    if plan is None:
        return None
    nodes = plan.nodes()
    for i, node in enumerate(nodes):
        if node.status != DONE:
            continue
        has_dependent = any(later.passthrough == node.passthrough for later in nodes[i + 1:])
        if not has_dependent:
            continue
        if os.path.exists(node.where):
            continue
        return Finding(
            pattern_id="gate.stale_establisher",
            file=node.where,
            line=0,
            level="advisory",
            message=(
                f"establisher {node.id!r} is recorded DONE but {node.where!r} no longer "
                f"exists on disk -- a dependent on passthrough {node.passthrough!r} would "
                f"read this gap as satisfied; re-establish it before trusting that dependency"
            ),
        )
    return None


CHECK = Check(
    id="gate.stale_establisher",
    applies_at="Stop",
    posture=ADVISE,
    run=lambda ctx: check(ctx.plan),
)
