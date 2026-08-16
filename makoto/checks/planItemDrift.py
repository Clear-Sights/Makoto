"""makoto.checks.planItemDrift -- ADVISORY reminder of open PLAN/TASK-LABELED commitments
("§9.3", "Task #19") a real session hit: a forward promise phrased as a section/task reference,
never a file path, was silently dropped and never appeared in ANY commitment store because
`session/commitments.py`'s sourcer requires a file-shaped location and found none.

`session/planItems.py` sources/discharges these purely textually (no filesystem ground truth
exists for a label); this check surfaces whatever is still open at Stop time as a reminder, ADVISORY
tier ONLY -- unlike `gate.advance` (which blocks on a verifiable file-vs-filesystem contradiction),
a label's "still open" state here is a weaker, textual-only signal with no corpus-measured FP rate
yet, so it must never block (same "advisory over blocking" policy `selfWiredCheck.py`/
`staleEstablisher.py` already follow, and the same caution the design review flagged for any
chat-prose-sourced obligation).
"""
from __future__ import annotations

from typing import Optional

from makoto.core.schema import Finding


def plan_item_drift_gate(open_items: list) -> Optional[Finding]:
    """Fire iff any plan-item commitment is still OPEN for this session -- a gentle, named
    reminder, never a block. `open_items=[]` (nothing open) is silent."""
    if not open_items:
        return None
    labels = ", ".join(i["label"] for i in open_items[:8])
    more = f" (+{len(open_items) - 8} more)" if len(open_items) > 8 else ""
    return Finding(
        pattern_id="gate.plan_item_drift",
        file="",
        line=0,
        level="advisory",
        message=(
            f"plan/task-labeled commitment(s) still open: {labels}{more}. A textual-only signal "
            f"(no filesystem ground truth for a label) -- confirm each is genuinely still pending, "
            f"not silently dropped."
        ),
        retry_hint="Mark each done (a first-person past-tense statement naming it) or retract it explicitly.",
    )


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.plan_item_drift", applies_at="Stop", posture="ADVISE",
               eats=frozenset({"open_plan_items"}),
               may_block=True, run=lambda c: plan_item_drift_gate(getattr(c, "open_plan_items", None) or []))
