"""makoto.checks.unknownRefSwitch -- gate.unknown_ref_switch, register entry
`D12 PRESERVE TO VOLATILE`.

HEAD was moved to a ref nothing in this session had printed. The entry's demand is that what must
survive a boundary be named before the boundary is crossed; switching a ref IS the boundary, and
the thing that must survive it is the work in the tree. Keel states this as clause U09
(`clear-sights/keel`, `plugin/keel/clauses.json`): *"HEAD moved to a ref nothing in this session
observed; print the ref before the next act."* Ward reaches the same entry from the other side
(`ward.forbidden_location`, a write to a protected or out-of-cwd location); this gate takes the
ref-switch side because that is the boundary makoto's own record shows.

WHY MAKOTO'S MAP SAID OUT-OF-SUBJECT, AND WHY THAT WAS THE WRONG BOUNDARY. The row read
"durability of a copy across a boundary makoto does not cross", which is right about a copy into
a tmpfs or a container layer. It is wrong that makoto crosses no boundary: a `git checkout` or
`git switch` in the session's own Bash record is a boundary crossed in front of it, and whether
the ref was ever printed first is two commands on the record.

ADVISORY TIER, NEVER BLOCK: a checkout of a branch the agent just created, or one named in the
request itself, is legitimately unprinted, and no corpus-measured false-positive rate exists.
"""
from __future__ import annotations

import re

from makoto.vocab import Finding
from makoto.kit import unmet_obligation_gate, command_matches

# Moving HEAD. `git checkout <ref>` and `git switch <ref>` are the two forms; `git checkout --`
# and `git checkout -- <path>` restore a FILE and move nothing, so they are excluded by
# requiring the argument not to start with a dash.
_REF_SWITCH_RX = re.compile(r"\bgit\s+(?:checkout|switch)\s+(?!-)")
# Printing the ref. Keel's U09 names exactly these forms; `git status` and `git log` are NOT
# here, because neither names the ref being switched TO.
_REF_PRINT_RX = re.compile(r"\bgit\s+(?:rev-parse|branch|show-ref|for-each-ref|ls-remote)\b")


# `kit.command_matches` is the one body for "this event's command matches a regex" -- four
# copies of it appeared the moment this batch landed and the duplicate-function law caught them.
_is_ref_switch = command_matches(_REF_SWITCH_RX)
_is_ref_print = command_matches(_REF_PRINT_RX)


unknown_ref_switch_gate = unmet_obligation_gate(
    act=_is_ref_switch,
    guard=_is_ref_print,
    pattern_id="gate.unknown_ref_switch",
    message=("HEAD was moved to a ref that nothing in this session had printed — switching a ref "
             "is a boundary, and what has to survive it was never named."),
    retry_hint=("Print the refs first (`git rev-parse --verify <ref>`, `git branch`, "
                "`git show-ref`) so the switch is to something known."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unknown_ref_switch", applies_at="Stop", posture="ADVISE", may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: unknown_ref_switch_gate(c.history))
