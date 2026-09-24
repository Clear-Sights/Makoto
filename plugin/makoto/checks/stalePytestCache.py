from __future__ import annotations
from typing import Optional

from makoto.vocab import Finding
from makoto.vocab import _ADV_FORWARD_RX, _NEGATION_RX, _SENTENCE_SPLIT_RX, _TEETH_FRAME_RX
from makoto.substrate.claims import whole_suite_pass_claim
from makoto.substrate.pytest_cache import stale_failing_node
from makoto.kit import unwitnessed

# SHAPE = OTHER_POINT: the witness is a second reading of the same subject on the filesystem --
# pytest's own on-disk lastfailed record -- never an act exercised by this check itself.
SHAPE = "OTHER_POINT"

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


# The text owes a witness that pytest's own on-disk record agrees, but ONLY once it carries a
# clean whole-suite pass-claim: no claim at all, a forward/conditional or negated framing, or a
# teeth-framed (deliberately-induced-failure) window around it, each mean nothing is claimed here
# in the first place. One expression by construction (module-level lambda, not `def`: the design
# pins this module's top-level function count at 1, `stale_pass_gate` alone), built with `:=` so
# `m`/`lead` are each computed once, same as the old stepwise-`if`/`return ()` body:
#   Sentence-prefix guard, GATE-LOCAL (sentinel c): the shared signal's forward/negation window
#   stops at the last comma — right for green_claim (its conjunct is a recorded red RUN), wrong
#   here, where "Once I fix the import, the tests pass" (and "It is not the case that, as of this
#   run, all tests pass") coexist with a live red lastfailed by construction. The WHOLE leading
#   sentence is scanned — split over the full prefix, no fixed lookback cap, so a long leading
#   clause cannot truncate away the conditional head — for BOTH the forward frame and a negation:
#   a DENY here asserts "claim says the whole suite passes", so both frames make that false.
owes = lambda text: ((True,) if (
    (m := whole_suite_pass_claim(text)) is not None
    and not _ADV_FORWARD_RX.search(lead := _SENTENCE_SPLIT_RX.split(text[:m.start()])[-1])
    and not _NEGATION_RX.search(lead)
    and not _TEETH_FRAME_RX.search(text[max(0, m.start() - _TEETH_WINDOW):m.end() + _TEETH_WINDOW])
) else ())
# No event here pays the claim directly: the witness is seeded once, in `paid`, from pytest's own
# on-disk lastfailed record (see `stale_pass_gate`) -- a second, independent reading of the same
# subject, not a fresh event in this stream.
pays = lambda _text: None


def stale_pass_gate(text, *, cwd=None) -> Optional[Finding]:
    """Fire iff a clean whole-suite pass-claim coexists with a LIVE failing node in pytest's own
    lastfailed record under `cwd`. Silent on: no/subset/negated/forward/quoted claim, a teeth-framed
    claim, a missing or green cache, and a stale (deleted-test) record."""
    if not text or not cwd:
        return None
    # The disk lookup is the expensive step (latency contract, module docstring): `paid`'s lambda
    # is only ever CALLED once `owes(text)` has already survived every cheaper text-only guard, so
    # the common (no-claim) path still never touches disk.
    for _ev, _subject in unwitnessed(
            (text,), owes=owes, pays=pays,
            paid=(lambda _s: stale_failing_node(cwd) is None,)):
        node = stale_failing_node(cwd)
        return Finding(
            pattern_id="gate.stale_pass",
            file=node.split("::", 1)[0],
            line=0,
            level="error",
            message=("Claim says the whole suite passes, but pytest's own lastfailed record names "
                     f"{node} as failing and that test still exists — re-run the suite and cite the "
                     "green result, or retract the claim."),
            retry_hint=f"Re-run the full suite (or {node}) and cite the green output, or narrow/retract the claim.",
        )
    return None


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.stale_pass", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="LIVE_QUERY",
               eats=frozenset({"text", "cwd"}),
               run=lambda c: stale_pass_gate(c.text, cwd=c.cwd))
