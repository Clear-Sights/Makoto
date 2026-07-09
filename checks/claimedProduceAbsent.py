from __future__ import annotations
import re
from typing import Optional
from makoto.checks import detect_locations, normalize_path
from makoto.core.schema import Finding
from makoto.core.lexicons import (
    _PRODUCE_VERB_RX, _BE_AUX_RX, _CLAUSE_BREAK_RX, _FORWARD_FRAME_RX, _NEG_FRAME_RX,
)
from makoto.substrate._shared import _BIND_BEFORE, _discharged
from makoto.substrate._shared import StopCheck


# A subordinate-clause marker or a READ/relational FRAME appearing in the verb->path gap means an
# intervening noun phrase + clause separates the produce verb from the path: the verb governs a
# DIFFERENT direct object ("updated the logic so … config.yaml", "wrote the handler to read from
# settings.json"), and the path is an inert reference (a read source, a constraint), not the
# authored object. A genuine production claim ("I wrote config.yaml", "created `handler.py`",
# "added X to `src/auth.py`") has either an essentially-empty gap (whitespace / article / quote /
# adjective) or a production-DESTINATION preposition before the path.
#
# Deliberately NOT in this set: a bare `to` / `from` / `that`. Those are the canonical
# production-target prepositions — "added the handler TO src/auth.py", "wrote the migration TO
# 0007.sql" are real production claims, not references. Their referencing uses are caught by the
# fuller frame instead: `read(s) from` (the read FP), `so` / `matches` / `requires` (the
# subordinate-clause FP). Including bare `to`/`from` over-narrowed and silenced live TPs
# (FP remediation 2026-06-25; tests/test_gates.py + tests/test_substrate_teeth.py pin the TPs).
_PRODUCE_OBJ_SEP_RX = re.compile(
    r"\b(?:so|against|match(?:es|ing)?|reads?\s+from|requires?|"
    r"according\s+to|based\s+on|conform(?:s|ing)?\s+to)\b", re.I)


def _production_claim_location(text):
    """Return the first located path that is the direct object of an ACTIVE first-person
    production claim, else None.

    Required structure (the 'make it clearer' fix for the measured FP): a produce verb sits
    BEFORE the path, in the SAME clause, in active voice — "I created `X`", "Wrote `X`". A
    path is INERT when no produce verb governs it (a heading, a reference, a deliverable
    list), when the verb is passive/copular ("`X` was written", "it's wired"), when a clause
    break separates them ("deletions landed; … the `X`"), or in a forward/negated frame
    ("will add `X`", "didn't add `X`"). This is the verifiable core: a claim the assistant
    itself produced this specific file."""
    if not text:
        return None
    for loc, a, b in detect_locations(text):
        before = text[max(0, a - _BIND_BEFORE):a]
        for vm in _PRODUCE_VERB_RX.finditer(before):
            pre = before[:vm.start()]
            if _BE_AUX_RX.search(pre):
                continue                              # passive/copular -> not a self-production claim
            between = before[vm.end():]
            if _CLAUSE_BREAK_RX.search(between):
                continue                              # verb governs a different clause's noun
            if _PRODUCE_OBJ_SEP_RX.search(between):
                continue                              # subordinator/read-frame separates verb and
                                                      # path -> path is a referenced source, not the
                                                      # verb's direct object (the measured FP)
            near = pre[-40:]
            if _FORWARD_FRAME_RX.search(near):
                continue                              # "will add X" -> a plan, not a claim
            if _NEG_FRAME_RX.search(near):
                continue                              # "didn't add X" -> admission (2.8), not a false claim
            return loc
    return None
def completion_gate(text, *, touched_keys, fs_exists=None, empty_keys=None, fs_size=None) -> Optional[Finding]:
    """Fire iff the assistant CLAIMS it produced a specific file (a produce verb governs a
    located path, non-forward, non-negated) but that file is neither in the results ledger
    nor on disk — a verifiable contradiction between the word and the world.

    What is INERT (the measured-FP fix, by being clearer not by firing less):
      - a bare done-word with no location              (nothing to verify)
      - a path with no governing produce verb           (a heading, a reference, a code
                                                          listing, a subagent's deliverable)
      - a non-path token (version/SHA/duration/task-id) (detect_location no longer matches it)
      - a forward/negated frame                          ("will add X", "didn't add X")
    A produced-claim that IS touched, or that the filesystem confirms, is silent (fail-open).
    Only an unbacked production claim bites.
    """
    loc = _production_claim_location(text)
    if not loc:
        return None                                  # no verifiable production claim -> inert
    if _discharged(loc, touched_keys, fs_exists, empty_keys=empty_keys, fs_size=fs_size):
        return None                                  # verified (ledger) or fail-open (filesystem)
    loc_n = normalize_path(loc)
    return Finding(
        pattern_id="gate.completion",
        file=loc_n,
        line=0,
        level="error",
        message=(f"Claim states {loc_n} was produced, but it is neither in the results "
                 f"ledger nor on disk — the word must match the world."),
        retry_hint="Produce/touch the cited location, or retract with a checked reason.",
    )


GATE = StopCheck(
    id="gate.completion",
    fn=completion_gate,
    run=lambda c: completion_gate(c.text, touched_keys=c.touched, fs_exists=c.fs_exists, empty_keys=c.empty, fs_size=c.fs_size),
)


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.completion", applies_at="Stop", posture="BLOCK", run=GATE.run)
