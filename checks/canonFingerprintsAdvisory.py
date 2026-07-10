"""gate.canon_fingerprints_advisory -- SPEC-5 Task 9 (Makoto absorbs Assay): the ADVISE-tier half
of the 17 in-scope canon session fingerprints (of the original 27-fingerprint THE_CANON,
REF-lever-graded-primitives/signalminer/grade_planted.py) ported onto Makoto's real Stop-gate
observable surface. See makoto/checks/_canonAtoms.py's module docstring/BLOCK_IDS comment for the
full scope-cut and posture-citation trail: these 13 either rest on a soft/claim atom the gold-oracle
finding doc's robust core does not name, or are among the doc's explicitly-named WORST DISQUALIFIED
fingerprints (nogreen_secret_testedit, red_no_green, claim_secret, claim_revert) -- so per SPEC-5's
own total-retention rule they stay in the catalog, evaluated and recorded, but NEVER block.

Sibling of canonFingerprints.py (the BLOCK-tier half); see that module's docstring for why this is
two gate modules instead of one (tests/test_stop_gate_level_invariant.py's one-gate-id/one-fixed-
level invariant). This id is named in that test's own _ADVISORY_ALLOWLIST, the same mechanism
gate.self_wired (FD6) already uses for its own advisory-only tier.
"""
from __future__ import annotations

from typing import List

from makoto.substrate._canonAtoms import calls_from_history, fired_canon_fingerprints
from makoto.core.schema import Finding


def canon_fingerprint_advisory_gate(text, history) -> List[Finding]:
    """One ADVISORY (never blocking) Finding per non-robust-core canon fingerprint that fires on
    this session's call stream. Silent (empty list) when none fire."""
    calls = calls_from_history(history)
    out: List[Finding] = []
    for name, formula, is_block in fired_canon_fingerprints(calls, text or ""):
        if is_block:
            continue
        out.append(Finding(
            pattern_id="gate.canon_fingerprints_advisory",
            file="", line=0, level="advisory",
            message=(f"canon.{name}: {formula} -- a gaming-shaped session fingerprint fired. "
                      f"ADVISORY only: this fingerprint rests on a soft/claim atom or is among the "
                      f"gold-oracle finding's named disqualified fingerprints, so it is recorded "
                      f"but never blocks."),
            retry_hint="Advisory only -- review the flagged behavior; this never blocks a turn.",
        ))
    return out


from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.canon_fingerprints_advisory", applies_at="Stop", posture="ADVISE",
               may_block=True, run=lambda c: canon_fingerprint_advisory_gate(c.text, c.history))
