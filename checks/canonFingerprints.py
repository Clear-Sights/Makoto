"""gate.canon_fingerprints -- SPEC-5 Task 9 (Makoto absorbs Assay): the BLOCK-tier half of the 17
in-scope canon session fingerprints (of the original 27-fingerprint THE_CANON,
REF-lever-graded-primitives/signalminer/grade_planted.py) ported onto Makoto's real Stop-gate
observable surface. See makoto/checks/_canonAtoms.py's module docstring for the full scope-cut
(10 of 27 need unimplemented atoms, not ported) and porting-fidelity notes, and its BLOCK_IDS for
the citation trail on exactly which 4 of the 17 are blocking-capable by construction.

LOADER-SHAPE DECISION (deliberate divergence from the ticket's literal "ONE new file" framing,
discovered while implementing, not a preference): the 17 in-scope fingerprints split BLOCK/ADVISE,
but tests/test_stop_gate_level_invariant.py enforces "one gate id -> one fixed Finding.level"
("error", unless the id is named in its advisory allowlist) -- a single mixed-posture module would
violate that invariant the moment both tiers fired in the same turn. Resolution: TWO gate modules
(this one, BLOCK-only; canonFingerprintsAdvisory.py, ADVISE-only), sharing their atom/decode logic
via the package-plumbing file _canonAtoms.py (underscore-prefixed like _shared.py, so
checks._loader's scan skips it -- not itself a detector). Both are flat files directly in checks/,
so SPEC-5's "flat checks/, no sub-package" layout rule still holds.
"""
from __future__ import annotations

from typing import List

from makoto.checks._canonAtoms import calls_from_history, fired_canon_fingerprints
from makoto.checks._shared import StopCheck
from makoto.schema import Finding


def canon_fingerprint_block_gate(text, history, *, transcript_path=None, session_id=None,
                                 state_root=None) -> List[Finding]:
    """One BLOCKING Finding per robust-core canon fingerprint that fires on this session's call
    stream (see _canonAtoms.BLOCK_IDS) -- UNLESS a qualifying ack-block discharges it (Task 2
    slice 5, FABLE DECISION Option A): a session-level fingerprint over immutable recorded
    history has no other legitimate discharge (narrowing the detector voids its 0-FP
    certificate; self-disabling normalizes the one action Makoto must never normalize), so once
    fired it would otherwise re-fire at every subsequent Stop for the rest of the session.
    `makoto.ackblock.find_ack_block` re-derives the discharge from the HOST-WRITTEN transcript
    every time (never trusted from chain content) -- a found ack is chain-appended for the
    audit/receipt trail via `record_ack_block_if_new`, but the discharge decision itself is
    always freshly re-derived, never read back from that row. Silent (empty list) when no
    fingerprint fires, or every fired one is acked."""
    calls = calls_from_history(history)
    out: List[Finding] = []
    for name, formula, is_block in fired_canon_fingerprints(calls, text or ""):
        if not is_block:
            continue
        ack = None
        try:
            import makoto.ackblock as _ackblock
            ack = _ackblock.find_ack_block(name, transcript_path=transcript_path,
                                           session_id=session_id, root=state_root)
        except Exception:
            ack = None
        if ack is not None:
            try:
                _ackblock.record_ack_block_if_new(ack, session_id=session_id, root=state_root)
            except Exception:
                pass
            continue
        out.append(Finding(
            pattern_id="gate.canon_fingerprints",
            file="", line=0, level="error",
            message=(f"canon.{name}: {formula} -- a robust-core gaming-shaped session fingerprint "
                      f"fired (0-FP on both the planted-clean and real-Claude-gold negative sets, "
                      f"per REF-lever-graded-primitives' gold-oracle certification)."),
            retry_hint=(f"This session's call stream matches a certified gaming-shaped fingerprint. "
                        f"Re-examine the flagged behavior (a suppressed check, a destructive "
                        f"command, or an unresolved gap between claim and evidence) before "
                        f"continuing, OR if the flagged action was legitimate and already fully "
                        f"re-examined, say exactly `makoto release.operator {name}: <reason>` in a "
                        f"real (non-tool, non-quoted) reply -- the only discharge this gate can "
                        f"honor, per Task 2 slice 5 / D8a."),
        ))
    return out


GATE = StopCheck(
    id="gate.canon_fingerprints",
    fn=canon_fingerprint_block_gate,
    run=lambda c: canon_fingerprint_block_gate(
        c.text, c.history, transcript_path=c.transcript_path,
        session_id=c.session_id, state_root=c.state_root),
)


from makoto.checks._loader import Check as _Check
CHECK = _Check(id="gate.canon_fingerprints", applies_at="Stop", posture="BLOCK", run=GATE.run)
