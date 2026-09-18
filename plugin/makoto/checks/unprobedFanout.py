"""makoto.checks.unprobedFanout -- gate.unprobed_fanout, register entry `B11 BASELINE UNTAKEN`.

Work was dispatched to a subagent and nothing in this session had read, globbed or grepped
first, so the brief was written from assumption. The register's demand is a baseline taken
before the measurement; Keel states the same point as clause D01 (`clear-sights/keel`,
`plugin/keel/clauses.json`), whose deny reason is the sentence this gate is named for: *"a brief
written from assumption returns work built on it, and the result is inherited whole."*

WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS THE WRONG CHANNEL. The row read "a
baseline run is not on any channel makoto reads", which is true of a BASELINE MEASUREMENT -- a
with-and-without number. It is not true of the baseline this clause means, which is a read of
the ground before work is dispatched onto it, and that is entirely on the record makoto already
reads: a Task/Agent event, and a Read/Glob/Grep event before it.

ADVISORY TIER, NEVER BLOCK. A subagent dispatched for pure exploration legitimately has nothing
to read first -- that is the whole point of sending it -- so an unguarded dispatch is a real
signal with a real benign class, and no corpus-measured false-positive rate exists for it yet.
Same "advisory over blocking" policy `selfWiredCheck.py`, `staleEstablisher.py` and
`planItemDrift.py` already follow. Promoting it to BLOCK needs a measured FP rate, not a
preference.
"""
from __future__ import annotations

from typing import Optional

from makoto.vocab import Finding
from makoto.kit import unmet_obligation_gate

# The dispatch tools. `Task` is the documented subagent tool name; `Agent` is the same act under
# the name this harness reports, and both are accepted rather than guessed between -- a closed
# vocabulary whose miss is a RECALL bound (a dispatch under some third name reads as no dispatch
# and the gate goes quiet), never a false block.
_DISPATCH_TOOLS = frozenset({"Task", "Agent"})
# The reads that pay the obligation. Keel's D01 names exactly these three.
_PROBE_TOOLS = frozenset({"Read", "Glob", "Grep"})


def _is_dispatch(ev: dict) -> bool:
    return ev.get("tool_name") in _DISPATCH_TOOLS


def _is_probe(ev: dict) -> bool:
    return ev.get("tool_name") in _PROBE_TOOLS


unprobed_fanout_gate = unmet_obligation_gate(
    act=_is_dispatch,
    guard=_is_probe,
    pattern_id="gate.unprobed_fanout",
    message=("Work was dispatched to a subagent and no Read, Glob or Grep appears earlier in "
             "this session's recorded events — the brief was written from assumption, and work "
             "built on an assumed baseline is inherited whole."),
    retry_hint=("Read, glob or grep the ground before dispatching, so the brief describes what "
                "is there; or confirm the dispatch was itself the exploration."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unprobed_fanout", applies_at="Stop", posture="ADVISE", may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: unprobed_fanout_gate(c.history))
