"""makoto.checks.staleEstablisher -- the ground-truth staleness detector (ADVISORY tier,
NEVER BLOCK; inert until a project declares a plan). Ported BY SHAPE (rule 5) from
`assay/assay/patterns/stale_establisher.py`, re-homed onto Makoto's own
`substrate._planNode.Plan`.

Fires when a plan node's establisher is recorded DONE but the artifact it named no longer
exists on disk -- the one gap `substrate._planNode.Plan`'s pure name->status scan cannot see,
because a node's `status` is a claim about history, never a live filesystem read. This is the
ONE deliberate departure from every other check's content-blind, filesystem-blind design (an
`os.path.exists` call); the only thing gating it is the declared plan itself -- given one it
runs on EVERY Stop, with no per-check enable/disable switch. DETECTIVE tier: a fired verdict
is an ADVISORY, never a deny -- escalating this to a blocking tier is a product decision left
to the caller, not made here.

WIRING: discovery is the ORDINARY one -- `registry.load_checks(edge="Stop")` finds this
module's `CHECK` like every other Stop check, and `context.run_stop_checks` appends its Finding
to the audited-but-never-blocking list. What keeps it out of the blocking tier is `may_block`
staying at its `False` default: `dispatch._blocking_gate_ids()` is `load_checks(edge="Stop")`
FILTERED on `may_block`, so this pattern_id can never enter it whatever `.level` its own Finding
carries -- STRUCTURALLY incapable of blocking, not merely labeled advisory (pinned by
`tests/test_stale_establisher.py::test_never_discovered_as_a_blocking_stop_gate`). Before the
2026-07-10 discovery unification this module was instead a direct-call carve-out, because the
then-current `load_stopchecks()` GATE discovery made every id it found auto-BLOCK by
construction ("discovered<=>live<=>blocking") -- exactly the tier this check must never enter.
That mechanism is gone and the carve-out with it; the never-blocks guarantee now rests on
`may_block=False` alone. Being an ordinarily discovered named check module, this file IS subject
to the same L2 import firewall as its siblings (tests/test_import_direction.py -- notably, no
reaching into the sibling `makoto.state.plan` store).

Reads: the declared Plan (never mutated) and the existence/size of each DONE node's `where`.
An empty artifact is not an establisher: it supplies none of the work a dependent needs.
"""
from __future__ import annotations

import os
from typing import Optional

from makoto.registry import Check
from makoto.kit import live_query_finding
from makoto.substrate._planNode import DONE, Plan
from makoto.registry import POSTURE_ADVISE
from makoto.vocab import Finding


def check(plan: Optional[Plan]) -> Optional[Finding]:
    """Fire iff a DONE node's `where` is missing from disk AND a later node shares its
    passthrough (a real dependent whose gap-check would wrongly read as satisfied) -- else
    `None`. `plan=None` (no declared plan) is inert.

    Walks the plan in declared order; for each DONE node, checks whether any LATER node shares
    its passthrough (per the same recurrence rule `substrate._planNode` reads) and, only then,
    whether the establisher's `where` still exists on disk (the expensive/impure check runs
    last, only when a dependent makes it matter). The first such contradiction fires; a plan
    with none is an affirmative clean pass (`None`)."""
    if plan is None:
        return None
    nodes = plan.nodes()
    # Last plan-index at which each passthrough-name occurs. Later entries overwrite earlier
    # ones, so `last_use[p] > i` is exactly "some LATER node shares this name" -- the same
    # answer as rescanning `nodes[i + 1:]` per DONE node, without that scan's O(n) slice COPY
    # on the Stop hot path.
    last_use = {node.passthrough: i for i, node in enumerate(nodes)}
    for i, node in enumerate(nodes):
        if node.status != DONE:
            continue
        if last_use[node.passthrough] <= i:
            continue          # no dependent -- nobody would misread this gap as satisfied
        # A missing locator is malformed stored state, not evidence about the empty path. An
        # empty artifact is likewise not an established dependency: every other artifact-backed
        # commitment treats zero bytes as undelivered.
        if not node.where:
            continue
        if os.path.exists(node.where) and os.path.getsize(node.where) > 0:
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


run = live_query_finding(query=lambda plan: check(plan), posture_label="gate.stale_establisher")

CHECK = Check(
    id="gate.stale_establisher",
    applies_at="Stop",
    posture=POSTURE_ADVISE,
    eats=frozenset({"plan"}),
    run=run,
    tests="LIVE_QUERY",
)
