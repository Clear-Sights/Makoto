"""makoto.checks.pastedFix -- gate.pasted_fix, register entry `H3 FIX DRAWN FROM FIXES`.

The register states the fault as *"a change reasoned from other changes"* against the rule
*"order by dependence; one change per pass"*. The same repair landed at a second site with
nothing run in between, so the second site's correctness was INFERRED from the first rather
than checked -- whatever the first landing taught was assumed to transfer.

THE NAIVE READING IS INDISCRIMINATE AND IS NOT WHAT THIS BUILDS, and a number says so. Read as
"two or more edits with no verifier run between them", the rule fires on 136 of this tree's own
185 non-merge commits -- 73.5%, which is simply what writing code looks like. Measured before a
line was written; the pass is in the commit that added this file.

WHAT THE RECORD CAN DECIDE, and the three narrowings, each with the rate it bought over those
same 185 commits. A commit stands in for one session's introduced text: it over-counts in one
direction (a session may span commits) and under-counts in the other, but it is real text
introduced by real sessions on this tree, and it is the only such record there is.

  1. THE SAME TEXT, not merely two edits -- a normalized block reaching two DISTINCT files.
                                                                        73.5% -> 9.2%
  2. A CHANGE TO WHAT EXISTS -- `Edit`/`MultiEdit` only. A fix is edited into a file that is
     already there, while a file being WRITTEN carries the house import header; admitting
     written files is what puts `from __future__ import annotations` in front of the gate.
                                                                         9.2% -> 3.8%
  3. SUBSTANCE -- the block must carry a line that is not a comment, an import or a decorator.
     A comment quoted at two sites is prose with one home, which is `F2`'s subject, not a
     repair whose correctness was inferred.                              3.8% -> 3.2%

THE GRAIN IS FOUR SUBSTANTIAL LINES, and it is a measurement rather than a preference. Over the
same corpus the reading fires on 21.1% of commits at one line -- the house predicate header and
every parallel call site -- and on NOTHING at eight, which is the dead vocabulary `scour`
deleted nineteen register entries for. At four, the fires are mostly the fault: of the six
commits it names, FOUR are one body pasted into a second and third module (the catalog's
claim-adjudication idiom, a predicate-resolver in two test modules, one test function and its
docstring in three), and the two that are not are a check-id list this architecture requires in
three homes and a house predicate header.

NAMED RECALL BOUND, and it follows from that grain: a repair SHORTER than four substantial lines
is not a finding. A one-line paste is a real instance of this entry and this gate does not see
it, because on this tree's own record a one-line repeat is indistinguishable from convention --
21.1% against 3.2%. The bound fails QUIET, which is the direction an advisory gate should fail.

THE DISCHARGE IS THE ORDER, and the order IS the check: a verifier run BETWEEN the two landings
pays the obligation; one before the first, or after the second, does not. That is the entry's
own rule -- *one change per pass* -- and it is exactly why this gate is NOT written on
`kit.unmet_obligation_gate`, whose guard, once seen, pays for the rest of the session. The
vocabulary of "a verifier ran" is `kit.ran_a_verifier`, unchanged and unwidened: the one home
`gate.unobserved_destruction` and `gate.relaunched_unchanged` already share.

DISCRIMINANT AGAINST `gate.unwitnessed_verifier`, the nearest same-edge survivor and the one
the merge pass pairs this with, which also turns on a verifier run: that gate reads the
verifier's REPORT and asks whether this session has ever seen it print a failure, so one clean
run with no red anywhere fires it while this gate has no mutation to look at at all. This one
reads MUTATIONS and asks only WHERE a run falls between two of them; the report is never
consulted, so a session that runs a RED verifier between two identical pastes is silent here
and loud there. `docs/MERGE-WITNESSES.tsv` carries an input for each direction.

`event.thrash_revert` is the nearest prose neighbour and the two are never paired, because it
is a Pre-tier check on a different edge: it asks whether a file is being written back to a
value it already held. Same word "again", different act -- one file returning to a prior state,
against one text reaching a second file.

ADVISORY TIER, NEVER BLOCK: the two benign classes measured above are real, common on this very
tree, and identical from the record -- a list the architecture keeps in three homes, and a house
convention wider than four lines -- and no corpus-measured false-positive rate exists.
"""
from __future__ import annotations

import re
from typing import Optional

from makoto.kit import decode_history_event, introduced_text, ran_a_verifier
from makoto.vocab import Finding

# A fix is a change to what already EXISTS. See narrowing 2 above for the rate this buys.
_EDIT_TOOLS = frozenset({"Edit", "MultiEdit"})
# How many contiguous substantial lines make a block. Measured; see the docstring. It is not a
# tunable threshold but the point where the reading stops naming convention and has not yet
# stopped naming anything.
_BLOCK_LINES = 4
# A line carrying no content of its own: closers, separators, a bare marker.
_TRIVIAL_RX = re.compile(r"^[\s)\]},:;#\"']*$")
# A line that travels as CONVENTION rather than as a repair: a comment, an import, a decorator,
# a docstring fence, a markup tag.
_CONVENTION_RX = re.compile(r"^(#|//|import\s|from\s+\S+\s+import\s|@|\"\"\"|'''|<)")


def _kept_lines(text: str) -> list:
    """`text`'s lines, whitespace-normalized, with the ones carrying nothing dropped.

    THE NORMALIZATION IS LOAD-BEARING: the margin goes and internal runs of whitespace collapse,
    so a paste that was REINDENTED at its second site is still the same paste. Without it, a fix
    moved into a deeper block reads as new text and the gate goes quiet on it.
    """
    out = []
    for line in (text or "").splitlines():
        flat = " ".join(line.split())
        if flat and not _TRIVIAL_RX.match(flat):
            out.append(flat)
    return out


def _blocks(lines: list) -> list:
    """Every contiguous run of `_BLOCK_LINES` kept lines that carries at least one substantial
    line -- see narrowing 3. A window of nothing but imports, comments and decorators is
    convention travelling, and convention travels legitimately.

    Each line's substance is decided ONCE, on its own, and the windows then slide a running
    count over those decisions. Written the obvious way -- an `any(...)` re-reading every line of
    every window -- it was scour's `C3 MASK` (one verdict hiding which item produced it) and it
    re-tested each line `_BLOCK_LINES` times; this is O(n) and says per line what it decided.
    """
    carries = [0 if _CONVENTION_RX.match(line) else 1 for line in lines]
    out = []
    substance = sum(carries[:_BLOCK_LINES])
    for i in range(len(lines) - _BLOCK_LINES + 1):
        if i:
            substance += carries[i + _BLOCK_LINES - 1] - carries[i - 1]
        if substance:
            out.append("\n".join(lines[i:i + _BLOCK_LINES]))
    return out


def _second_site_finding(block: str, first_file: str, second_file: str) -> Finding:
    head = block.split("\n")[0]
    return Finding(
        pattern_id="gate.pasted_fix",
        file=second_file,
        line=0,
        level="advisory",
        message=(
            f"The same change reached `{second_file}` after `{first_file}` with no verifier run "
            f"between the two landings, starting `{head}` — so the second site's correctness is "
            f"drawn from the first rather than checked."
        ),
        retry_hint=(
            "Run the verifier between the two landings, or order the change by dependence and "
            "make one per pass. A repair that transfers is a claim about the second site, and "
            "the first site's green is not evidence for it."
        ),
        snippet=head[:200],
    )


def pasted_fix_gate(history) -> Optional[Finding]:
    """Fire iff one block of introduced text reached a SECOND file with no verifier run between
    the two landings."""
    runs = 0
    landed = {}
    for row in history or ():
        ev = decode_history_event(row)
        if not isinstance(ev, dict):
            continue                     # fail open: an undecodable row could be the run
        if ran_a_verifier(ev):
            runs += 1
            continue
        if ev.get("hook_event_name") != "PostToolUse":
            continue
        tool = ev.get("tool_name", "")
        if tool not in _EDIT_TOOLS:
            continue
        tool_input = ev.get("tool_input")
        if not isinstance(tool_input, dict):
            continue
        path = str(tool_input.get("file_path", ""))
        for block in _blocks(_kept_lines(introduced_text(tool, tool_input))):
            before = landed.get(block)
            if before is None:
                landed[block] = (path, runs)
                continue
            where, when = before
            if where == path or when != runs:
                continue                 # the same file again, or a verifier ran between
            return _second_site_finding(block, where, path)
    return None


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.pasted_fix", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="PATTERN_MATCH",
               eats=frozenset({"history"}),
               run=lambda c: pasted_fix_gate(c.history))
