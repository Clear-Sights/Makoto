"""makoto.checks.unobservedDestruction -- gate.unobserved_destruction, register entry
`D14 UNDO UNPROVEN`.

Content was destroyed and no independent behaviour observer had run first, so there is nothing
against which the undo could be proven -- not the change, and not the state before it. Keel
states this as clause U20 (`clear-sights/keel`, `plugin/keel/clauses.json`): *"content was
destroyed and no independent behaviour observer ran first; run the relevant test or probe (a
report, PASS or FAIL) before the next act."*

WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHY THAT WAS A STRONGER QUESTION THAN THE ENTRY ASKS.
The row read "an undo's provability is not a channel makoto reads", which is true of proving the
undo. The countable question underneath is whether anything was OBSERVED before the destruction:
a verifier report, PASS or FAIL, is what makes a later undo checkable at all, and both the
destructive command and the verifier run are on the record makoto already holds.

ONE HOME FOR "DESTRUCTIVE". The classifier is `substrate._canonAtoms._is_destructive_argv`,
imported unchanged -- the same function `gate.canon_fingerprints`' `destructive_command` atom
uses, over `core._shell._shell_segments` -- the same splitter, reached directly because
`_canonAtoms._segments` keys on a Call dict this gate does not build. A second definition of destruction here would be `F2 TWO SOURCES OF TRUTH`, and its
documented scope cut (long-form `rm` stays outside, pinned in test_canon_atoms_destructive) is
inherited whole rather than re-litigated.

ADVISORY TIER, NEVER BLOCK: deleting scratch output, a build directory or a file created earlier
in the same session is destruction that owes no observer, and no corpus-measured false-positive
rate exists for the distinction.
"""
from __future__ import annotations

import re

from makoto.vocab import Finding
from makoto.kit import unmet_obligation_gate, command_of, ran_a_verifier
from makoto.substrate._canonAtoms import _is_destructive_argv
from makoto.core._shell import _shell_segments


def _is_destruction(ev: dict) -> bool:
    cmd = command_of(ev)
    if not cmd:
        return False
    return any(_is_destructive_argv(argv) for argv, _ in _shell_segments(cmd))


# The guard is `kit.ran_a_verifier`, the ONE definition of "something observed behaviour",
# shared with gate.relaunched_unchanged. Keel's U20 asks for a report, PASS or FAIL, because
# either one is an observation and only the absence of both leaves an undo unprovable -- which
# is why that primitive does not read the verdict.
_is_observer = ran_a_verifier


unobserved_destruction_gate = unmet_obligation_gate(
    act=_is_destruction,
    guard=_is_observer,
    pattern_id="gate.unobserved_destruction",
    message=("Content was destroyed and no verifier had run first — with no behaviour observed "
             "before the destruction, the undo cannot be proven against anything."),
    retry_hint=("Run the relevant test or probe to a report (PASS or FAIL) before a destructive "
                "act, so there is a pre-image to check an undo against."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unobserved_destruction", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: unobserved_destruction_gate(c.history))
