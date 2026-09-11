"""gate.canon_fingerprints -- SPEC-5 Task 9 (Makoto absorbs Assay): the BLOCK-tier half of the 17
in-scope canon session fingerprints (of the original 27-fingerprint THE_CANON,
REF-lever-graded-primitives/signalminer/grade_planted.py) ported onto Makoto's real Stop-gate
observable surface. See makoto/substrate/_canonAtoms.py's module docstring for the full scope-cut
(10 of 27 need unimplemented atoms, not ported) and porting-fidelity notes, and its BLOCK_IDS for
the citation trail on exactly which 4 of the 17 are blocking-capable by construction.

LOADER-SHAPE DECISION (deliberate divergence from the ticket's literal "ONE new file" framing,
discovered while implementing, not a preference): the 17 in-scope fingerprints split BLOCK/ADVISE,
but tests/test_stop_gate_level_invariant.py enforces "one gate id -> one fixed Finding.level"
("error", unless the id is named in its advisory allowlist) -- a single mixed-posture module would
violate that invariant the moment both tiers fired in the same turn. Resolution: TWO gate modules
(this one, BLOCK-only; canonFingerprintsAdvisory.py, ADVISE-only), sharing their atom/decode logic
via the package-plumbing file makoto/substrate/_canonAtoms.py (it sits in the substrate package,
outside the `checks/*.py` glob registry's `_candidate_files` scans, and is underscore-prefixed on
top of that -- not itself a detector). Both gate modules are flat files directly in checks/, so
SPEC-5's "flat checks/, no sub-package" layout rule still holds.
"""
from __future__ import annotations

from typing import List

from makoto.state.ledger import _event_instant, last_fired_ts, operator_window
from makoto.substrate._canonAtoms import BLOCK_IDS, _row_ts, calls_from_history, fired_canon_fingerprints
from makoto.vocab import Finding


def canon_fingerprint_block_gate(text, history, *, transcript_path=None, session_id=None,
                                 state_root=None) -> List[Finding]:
    """Block once per fingerprint occurrence, then evaluate only its new call window."""
    history = operator_window(history, transcript_path)
    out: List[Finding] = []
    for name in sorted(BLOCK_IDS):
        since = _event_instant(last_fired_ts(name, session_id=session_id, root=state_root))
        # Each fingerprint has its own boundary. Calls at the firing are already covered;
        # retain undated evidence because it cannot establish which window it belongs to.
        window = [row for row in history
                  if since is None or (ts := _event_instant(_row_ts(row))) is None or ts > since]
        formula = next((formula for fired_name, formula, _ in
                        fired_canon_fingerprints(calls_from_history(window), text or "")
                        if fired_name == name), None)
        if formula is None:
            continue
        out.append(Finding(
            pattern_id="gate.canon_fingerprints",
            file="", line=0, level="error",
            message=(f"canon.{name}: {formula} -- a robust-core gaming-shaped session fingerprint "
                      f"fired (0-FP on both the planted-clean and real-Claude-gold negative sets, "
                      f"per REF-lever-graded-primitives' gold-oracle certification)."),
            retry_hint=("Re-examine; a new call window starts at this firing; repeating the "
                        "pattern re-blocks. Check the flagged behavior: a suppressed check, "
                        "a destructive command, or an unresolved gap between claim and evidence."),
        ))
    return out


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.canon_fingerprints", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="CLAIM_VS_HISTORY",
               eats=frozenset({"text", "history", "transcript_path", "session_id", "state_root"}),
               run=lambda c: canon_fingerprint_block_gate(
                   c.text, c.history, transcript_path=c.transcript_path,
                   session_id=c.session_id, state_root=c.state_root))
