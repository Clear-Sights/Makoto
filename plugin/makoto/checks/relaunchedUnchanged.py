"""makoto.checks.relaunchedUnchanged -- gate.relaunched_unchanged, register entry
`E13 PARKED ON AN INHERITED CHANNEL`.

A worker was launched again after an earlier launch, and nothing between the two proved its
target had changed -- no verifier reported anything. The second launch inherits the first one's
channel: whatever the worker could not reach before, it still cannot, and a re-launch with
nothing changed is a wait dressed as an act. Keel states this as clause U02
(`clear-sights/keel`, `plugin/keel/clauses.json`): *"a worker was re-launched and nothing proved
its target changed since the failure: change something, then run the target's probe to a PASS,
before the next act."*

WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS THE WRONG CHANNEL. The row read "a
detached task's input channel is not on the record makoto reads", which is right about what the
worker itself received. This gate reads neither the channel nor the worker's output: it reads the
REPEAT, which is two dispatch events, and whether a verifier ran between them. Both are on the
record makoto already holds.

`min_acts=2` IS THE WHOLE POINT. The first launch owes nothing -- that is the act the clause
exists to permit. Only the second unguarded one is the costly thing, which is why the factory
carries the count rather than each clause re-deriving it.

ADVISORY TIER, NEVER BLOCK: dispatching two independent workers for two independent jobs is the
common benign case and looks identical here, and no corpus-measured false-positive rate exists.
"""
from __future__ import annotations

from makoto.vocab import Finding
from makoto.kit import unmet_obligation_gate, ran_a_verifier

_DISPATCH_TOOLS = frozenset({"Task", "Agent"})


def _is_relaunch(ev: dict) -> bool:
    return ev.get("tool_name") in _DISPATCH_TOOLS


# Same guard, same one definition: `kit.ran_a_verifier`. A verifier ran between the launches,
# verdict unread -- a report is the observation, and only the absence of any report leaves the
# re-launch resting on nothing.
_is_probe = ran_a_verifier


relaunched_unchanged_gate = unmet_obligation_gate(
    act=_is_relaunch,
    guard=_is_probe,
    min_acts=2,
    pattern_id="gate.relaunched_unchanged",
    message=("A worker was launched again with no verifier run anywhere before it — the second "
             "launch inherits the first one's channel, so nothing shows its target changed."),
    retry_hint=("Change something and run the target's probe to a report before re-launching; "
                "or confirm the two launches are independent jobs."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.relaunched_unchanged", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: relaunched_unchanged_gate(c.history))
