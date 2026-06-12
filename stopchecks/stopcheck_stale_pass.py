from __future__ import annotations
from typing import Optional

from makoto.schema import Finding
from makoto.lexicons import _ADV_FORWARD_RX, _SENTENCE_SPLIT_RX, _TEETH_FRAME_RX
from makoto.lib.claims import whole_suite_pass_claim
from makoto.lib.pytest_cache import stale_failing_node
from makoto.stopchecks._types import StopCheck

# gate.stale_pass — a WHOLE-SUITE pass-claim ✗ pytest's OWN on-disk failure record.
#
#     "All tests pass."   ✗   .pytest_cache/v/cache/lastfailed names a failing node
#                             whose test file + function STILL EXIST on disk.
#
# The claim-vs-ledger primitive with pytest itself as the ledger: lastfailed is written by the
# runner, not the assistant, so the contradiction is between the assistant's prose and the
# toolchain's own record. The existence filter is the staleness firewall (measured 42/42 on the
# real corpus): a node whose file or `def` is gone was refactored away — the record is stale
# evidence, not a live failure, and the gate stays silent (fail-open).
#
# WHEN: the pass-claim only exists in the final assistant message, so dispatch is the Stop hook.
# LATENCY CONTRACT (post-check-class, user-directed 2026-06-09): the gate's WORK is budgeted at
# the proposed post-check tier — a hard 200-300ms ceiling, target single-digit ms warm — NOT the
# permissive Stop tier it dispatches in. The evidence side is a literal direct-pointer lookup
# (one lastfailed read + at most 50 capped file reads; lib/pytest_cache pins the bounds), and the
# body is ordered cheapest-first so the common path never touches disk:
#   1. claim regex (no whole-suite claim -> exit; the dominant case)
#   2. teeth window (±160 chars around the claim vs lexicons._TEETH_FRAME_RX — a deliberately-
#      induced failure narrated next to the claim is mutation/teeth testing, not a contradiction)
#   3. ONLY THEN the disk lookup.
# tests/test_stale_pass_gate.py carries the measured-latency falsifier for the ceiling.

_TEETH_WINDOW = 160


def stale_pass_gate(text, *, cwd=None) -> Optional[Finding]:
    """Fire iff a clean whole-suite pass-claim coexists with a LIVE failing node in pytest's own
    lastfailed record under `cwd`. Silent on: no/subset/negated/forward/quoted claim, a teeth-framed
    claim, a missing or green cache, and a stale (deleted-test) record."""
    if not text or not cwd:
        return None
    m = whole_suite_pass_claim(text)
    if not m:
        return None
    # Sentence-prefix forward guard, GATE-LOCAL (sentinel c): the shared signal's forward window
    # stops at the last comma — right for green_claim (its conjunct is a recorded red RUN), wrong
    # here, where "Once I fix the import, the tests pass" coexists with a live red lastfailed by
    # construction. The whole leading sentence is scanned so the conditional head is seen.
    lead = _SENTENCE_SPLIT_RX.split(text[max(0, m.start() - 240):m.start()])[-1]
    if _ADV_FORWARD_RX.search(lead):
        return None                      # forward/conditional-framed claim, not a present assertion
    window = text[max(0, m.start() - _TEETH_WINDOW):m.end() + _TEETH_WINDOW]
    if _TEETH_FRAME_RX.search(window):
        return None                      # deliberately-induced failure framing around the claim
    node = stale_failing_node(cwd)
    if node is None:
        return None
    return Finding(
        pattern_id="gate.stale_pass",
        file=node.split("::", 1)[0],
        line=0,
        level="error",
        message=(f"Claim says the whole suite passes, but pytest's own lastfailed record names "
                 f"{node} as failing and that test still exists — re-run the suite and cite the "
                 f"green result, or retract the claim."),
        retry_hint=f"Re-run the full suite (or {node}) and cite the green output, or narrow/retract the claim.",
    )


GATE = StopCheck(
    id="gate.stale_pass",
    fn=stale_pass_gate,
    run=lambda c: stale_pass_gate(c.text, cwd=c.cwd),
)
