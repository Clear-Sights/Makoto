"""makoto.checks.unreadStructure -- gate.unread_structure, register entry `A3 POSITIONAL PAIRING`.

A traversal of structured data produced `null`, and nothing in this session had looked at the
structure first. The register's demand is to read the shape rather than assume the positions line
up; Keel states the same point as clause U10 (`clear-sights/keel`,
`plugin/keel/clauses.json`): *"a traversal of structured data produced null; look at the
structure before the next act."*

WHY MAKOTO'S MAP SAID OUT-OF-SUBJECT, AND WHY THAT WAS THE WRONG SUBJECT. The row read "pairing
of two sequences inside code makoto does not execute", which is right about a zip() in someone
else's source. It is not what this entry catches at the act grain: a `jq` or `python -c` that
reads a structured file and prints `null` is the pairing failing IN THIS SESSION, on the record
makoto already holds -- the command and what it printed.

`null` IS THE SIGNAL, and nothing narrower. A traversal that prints a wrong non-null value is
invisible here (it needs the intended value, which is not on any channel makoto reads) and a
traversal that prints nothing at all is excluded deliberately: an empty stdout is what a great
many correct commands produce. Only a literal JSON `null` as the whole of what was printed
counts. That is a RECALL bound, named, and it fails quiet.

ADVISORY TIER, NEVER BLOCK: a `null` can be the true answer to the question asked, and no
corpus-measured false-positive rate exists for the distinction.
"""
from __future__ import annotations

import re

from makoto.vocab import Finding
from makoto.kit import unmet_obligation_gate, response_text, command_of

# A structured-data traversal. `jq` is the canonical one; `python -c ... json` and `yq` are the
# same act under other programs. A closed vocabulary whose miss is a RECALL bound.
_TRAVERSAL_RX = re.compile(r"\b(?:jq|yq|json_pp)\b|python3?\s+-c\b[^\n]*\bjson\b")
# The structure query that pays the obligation: any of the shape-printing jq forms Keel's U10
# names, or a Read of the file.
_STRUCTURE_RX = re.compile(r"\b(?:jq|yq)\b[^\n]*(?:\bkeys\b|\btype\b|\bhas\s*\(|\blength\b|"
                           r"\bpaths\b|\bto_entries\b|-e\b)")
# What a failed traversal prints: a literal JSON null as the WHOLE output. `.strip()` has already
# run, so an anchored match is the whole of it.
_NULL_OUTPUT_RX = re.compile(r"\Anull\Z")


def _is_null_traversal(ev: dict) -> bool:
    cmd = command_of(ev)
    if not cmd or not _TRAVERSAL_RX.search(cmd):
        return False
    return bool(_NULL_OUTPUT_RX.match(response_text(ev)))


def _is_structure_read(ev: dict) -> bool:
    if ev.get("tool_name") == "Read":
        return True
    cmd = command_of(ev)
    return bool(cmd and _STRUCTURE_RX.search(cmd))


unread_structure_gate = unmet_obligation_gate(
    act=_is_null_traversal,
    guard=_is_structure_read,
    pattern_id="gate.unread_structure",
    message=("A traversal of structured data printed `null` and nothing in this session looked "
             "at the structure first — the positions were assumed to line up rather than read."),
    retry_hint=("Print a non-null datum from the file first (`jq 'keys'`, `jq 'type'`, "
                "`jq -e 'has(...)'`) or Read it, then re-run the traversal."),
)


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.unread_structure", applies_at="Stop", posture="ADVISE", may_block=True,
               tests="ACT_VS_GUARD",
               eats=frozenset({"history"}),
               run=lambda c: unread_structure_gate(c.history))
