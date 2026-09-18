"""makoto.checks.unasked_plan -- gate.unasked_plan, register entry
`G2 DETERMINED ASKED AS OPEN`.

A plan was presented and no question was asked this session, so whatever the request left
ambiguous was settled by guessing. The register's demand is that a determined thing not be
carried forward as open -- here in its live direction: the ambiguity WAS determinable by asking,
and the plan fixed it by assumption instead. Keel states the same point as clause P02
(`clear-sights/keel`, `plugin/keel/clauses.json`): *"reading files resolves what the repository
is, never what was wanted, and a plan is followed by default."*

WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS THE WRONG READING. The row read "needs the
question compared against what was derivable; that comparison is similarity", and that is true
of grading WHICH question should have been asked. It is not needed to grade whether ANY was:
an ExitPlanMode event, and an AskUserQuestion event before it, are both on the record makoto
already reads. The weaker, countable question is the one this gate asks.

ADVISORY TIER, NEVER BLOCK. A plan for a request that carried no ambiguity owes no question,
and no corpus-measured false-positive rate exists for the distinction yet. Same "advisory over
blocking" policy `selfWiredCheck.py`, `staleEstablisher.py` and `planItemDrift.py` follow.
"""
from __future__ import annotations

from typing import Optional

from makoto.vocab import Finding
from makoto.kit import unmet_obligation_gate

# Presenting a plan. A closed vocabulary whose miss is a RECALL bound, never a false block.
_PLAN_TOOLS = frozenset({"ExitPlanMode"})
# The ask that pays the obligation. Keel's P02 names exactly this one.
_ASK_TOOLS = frozenset({"AskUserQuestion"})


def _is_plan(ev: dict) -> bool:
    return ev.get("tool_name") in _PLAN_TOOLS


def _is_ask(ev: dict) -> bool:
    return ev.get("tool_name") in _ASK_TOOLS


unasked_plan_gate = unmet_obligation_gate(
    act=_is_plan,
    guard=_is_ask,
    pattern_id="gate.unasked_plan",
    message=("A plan was presented and no question was asked this session — reading the "
             "repository resolves what it is, never what was wanted, and a plan is followed by "
             "default, so an ambiguity settled by guessing is carried as if it were settled."),
    retry_hint=("Ask one question about the ambiguity before the plan is fixed; or confirm the "
                "request carried none."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unasked_plan", applies_at="Stop", posture="ADVISE", may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: unasked_plan_gate(c.history))
