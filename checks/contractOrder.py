"""makoto.checks.contractOrder -- PREVENTIVE plan-gap / stop gate over a declared Plan.

Ported BY SHAPE (rule 5 -- copy, never import) from `assay/assay/patterns/contract_order.py`,
re-homed onto Makoto's own `checks._planNode.Plan` + the `plans` sqlite table (SPEC-5 Makoto
absorbs Assay). contractOrder reads gaps-in-ledger, NOT a DAG: a dependency is a GAP read off
the plan BY PASSTHROUGH-NAME (`Plan.order_violation`/`Plan.unmet_deps`), never a declared edge
-- the sole home for that scan is `checks._planNode`, consulted here, never re-implemented.

TWO firing surfaces from ONE module, mirroring Assay's single `ContractOrder` class's two
guards:
  * the PRE gap guard (`predicate`, wired via `data/patterns.toml` + `_dispatch._run_predicates`,
    BLOCK): a Write/Edit/MultiEdit/NotebookEdit call advancing a plan node whose passthrough-
    establisher is not yet DONE is the partial-order contradiction.
  * the STOP remainder guard (`GATE`, discovered by `substrate._loader.load_stopchecks`; BLOCK by
    construction -- discovered<=>live<=>blocking, no shadow tier, `checks/_shared.py`): the
    turn ending with the plan's `remainder()` non-empty.

LAYERING FIREWALL: as a discovered Stop GATE this module is subject to the same L2-import
firewall every gate module is (`tests/test_gate_shape.py`'s `ALLOWED_IMPORT_ROOTS`) -- it never
imports `makoto.session.plan` (a sibling L2 store) directly. The PRE predicate instead reads the
`plans` table INLINE via its own `conn` argument (`_load_plan` below) -- a small, deliberate
duplicate of `plan.load_plan`'s SQL, this repo's own boundary law ("shapes are copied, never
imported") applied at this finer grain -- while the STOP side reads the already-loaded
`ctx.plan` that `_dispatch.run_stop_checks` populates once per event.
"""
from __future__ import annotations

import json
from typing import Optional

from makoto.checks import normalize_path
from makoto.substrate._loader import Check
from makoto.substrate._planNode import Plan
from makoto.core.schema import Finding

_LOCATING_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_LOCATION_KEYS = ("file_path", "notebook_path")


def _load_plan(conn, session_id: str) -> Optional[Plan]:
    """A small, deliberate duplicate of `plan.load_plan`'s SQL -- see module docstring
    (contractOrder is a discovered Stop GATE, so it may not import the sibling L2 `makoto.session.plan`
    store directly)."""
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT rows FROM plans WHERE session_id = ?", [session_id]
        ).fetchone()
    except Exception:
        return None
    if not row or not row[0]:
        return None
    try:
        rows = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    if not rows:
        return None
    return Plan.from_rows(rows)


def _event_location(tool_name: str, tool_input: dict) -> Optional[str]:
    """The normalized WHERE a locating call targets, or `None` when the call is not a locating
    advance -- reads `file_path`/`notebook_path` off the tool input, never argument meaning."""
    if tool_name not in _LOCATING_TOOLS:
        return None
    for key in _LOCATION_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return normalize_path(value)
    return None


def _gap_finding(plan: Plan, tool_name: str, loc: str) -> Optional[dict]:
    """`{"nid", "unmet"}` iff `loc` advances a declared node whose establisher is unmet, else
    `None`. Resolves the call's WHERE to the node it advances via `Plan.resolve`, then consults
    `Plan.order_violation` (the name->status gap scan `checks._planNode` owns)."""
    nid = plan.resolve(loc, tool_name)
    if nid is None or not plan.order_violation(nid):
        return None
    return {"nid": nid, "unmet": sorted(plan.unmet_deps(nid))}


def predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional[Finding]:
    """Pre-tool-call GAP guard: fire iff the call advances a declared node whose establisher
    (an earlier node sharing its passthrough-name) is not yet DONE."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    tool_name = current_event.get("tool_name", "")
    loc = _event_location(tool_name, current_event.get("tool_input") or {})
    if loc is None:
        return None
    plan = _load_plan(conn, current_event.get("session_id", ""))
    if plan is None:
        return None
    gap = _gap_finding(plan, tool_name, loc)
    if gap is None:
        return None
    return Finding(
        pattern_id=pattern.id,
        file=loc,
        line=0,
        level=pattern.fire_level,
        message=(
            f"contract gap: {gap['nid']!r} cannot run before the establisher(s) of its "
            f"passthrough are DONE -- unmet {gap['unmet']}; finish them first."
        ),
        retry_hint=pattern.retry_hint,
    )


def _stop_finding(plan: Optional[Plan]) -> Optional[Finding]:
    """Per-session STOP guard: fire iff the turn stops with the plan UNFINISHED, naming the
    remainder. `plan=None` (no declared plan) is inert."""
    if plan is None:
        return None
    remainder = sorted(plan.remainder())
    if not remainder:
        return None
    return Finding(
        pattern_id="gate.contract_order",
        file="",
        line=0,
        level="error",
        message=(
            f"contract not finished: cannot stop with open nodes {remainder} -- "
            f"finish them before stopping."
        ),
    )


RETRY_HINT = 'Finish the node(s) that establish this passthrough (the unmet ids named in the message) before advancing this one -- deps are gaps in the declared plan, read by passthrough name, never a declared edge.'
DESCRIPTION = 'declared-plan contract gap -- a Write/Edit/MultiEdit/NotebookEdit advances a plan node whose passthrough-establisher is not yet DONE'

CHECK = Check(id="gate.contract_order", applies_at="Pre", posture="BLOCK", run=predicate, predicate_module=__name__, keywords=('file_path', 'notebook_path'), retry_hint=RETRY_HINT, description=DESCRIPTION)

# This module's Stop-side surface shares the SAME id as its Pre-side CHECK above but fires at a
# different edge -- checks._loader.discover()'s EXTRA_CHECKS convention (the sole dual-surface
# case in the catalog) makes the Stop-side visible to the unified loader instead of needing a
# direct-call carve-out in run_stop_checks. may_block=True: this Stop-side surface used to be
# discoverable via the now-retired GATE/load_stopchecks() mechanism.
EXTRA_CHECKS = [
    Check(id="gate.contract_order", applies_at="Stop", posture="BLOCK", may_block=True,
          run=lambda ctx: _stop_finding(ctx.plan)),
]
