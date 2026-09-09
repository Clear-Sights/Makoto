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

from makoto.substrate._canonAtoms import calls_from_history, fired_canon_fingerprints
from makoto.vocab import Finding


def canon_fingerprint_block_gate(text, history, *, transcript_path=None, session_id=None,
                                 state_root=None) -> List[Finding]:
    """One BLOCKING Finding per robust-core canon fingerprint that fires on this session's call
    stream since the last operator message or explicit interruption (see _canonAtoms.BLOCK_IDS).
    A qualifying release.operator remains an optional per-fingerprint override, including for
    older history whose timestamps cannot establish the window.
    `makoto.state.ledger.find_ack_block` re-derives the discharge from the HOST-WRITTEN transcript
    every time (never trusted from chain content) -- a found ack is chain-appended for the
    audit/receipt trail via `record_ack_block_if_new`, but the discharge decision itself is
    always freshly re-derived, never read back from that row. Silent (empty list) when no
    fingerprint fires, or every fired one is acked."""
    # THE ATOM WINDOW. Atoms are existentials, so over a whole session they are monotone: once a
    # fingerprint has matched it can never stop matching, whatever the agent does next, and the
    # typed phrase becomes its only exit. Evaluating over the calls since the operator last spoke
    # makes it fire once, inform them, and reset when they next speak -- whatever they say --
    # firing again only if the agent repeats the pattern after being told. The agent cannot force
    # a reset: it cannot produce a genuine user turn. AliceLJY, issue #45's secondary half; #57.
    # Without a genuine message or explicit host interruption, keep the whole session.
    # `release.operator` remains the optional explicit override.
    try:
        import makoto.state.ledger as _ackblock
        history = _ackblock.operator_window(history, transcript_path)
    except Exception:
        pass
    calls = calls_from_history(history)
    out: List[Finding] = []
    for name, formula, is_block in fired_canon_fingerprints(calls, text or ""):
        if not is_block:
            continue
        try:
            import makoto.state.ledger as _ackblock
            ack = _ackblock.find_ack_block(name, transcript_path=transcript_path,
                                           gate_pattern_id="gate.canon_fingerprints",
                                           session_id=session_id, root=state_root, history=history)
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
                        f"continuing. Any new genuine operator message or explicit operator "
                        f"interrupt starts a new window; repeating the pattern there blocks again. "
                        f"For an optional explicit override of a reviewed finding, "
                        f"the human operator must say exactly "
                        f"`makoto release.operator {name}: <reason>` in a user turn "
                        f"(non-tool, non-quoted); an assistant reply cannot discharge this gate."),
        ))
    return out


from makoto.registry import Check as _Check
CHECK = _Check(id="gate.canon_fingerprints", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="CLAIM_VS_HISTORY",
               eats=frozenset({"text", "history", "transcript_path", "session_id", "state_root"}),
               run=lambda c: canon_fingerprint_block_gate(
                   c.text, c.history, transcript_path=c.transcript_path,
                   session_id=c.session_id, state_root=c.state_root))
