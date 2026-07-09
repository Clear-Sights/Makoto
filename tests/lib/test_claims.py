"""lib/claims.py (L1) — the renamed claim/admission primitives. Pins new names, old-names-gone,
behaviour, L1 purity."""
import ast
from pathlib import Path


def test_claims_exports_renamed_symbols():
    from makoto.substrate import claims
    for name in ("claims_done", "claims_success"):
        assert callable(getattr(claims, name)), name


def test_claims_old_names_are_gone():
    from makoto.substrate import claims
    for old in ("response_claims_done", "response_claims_success",
                "claim_is_unenumerated_completion", "admission_marker_match",
                "admission_marker_strengthened"):
        assert not hasattr(claims, old), f"no alias: {old}"


def test_claims_behaviour_preserved():
    from makoto.substrate.claims import claims_done, claims_success
    assert claims_done({"last_assistant_message": "All done."}) is True
    assert claims_done({"last_assistant_message": "I am not done."}) is False
    assert claims_success({"last_assistant_message": "I shipped it."}) is not None


def test_claims_is_L1_imports_only_L0():
    src = Path(__file__).resolve().parents[2] / "substrate" / "claims.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("makoto"):
            assert node.module == "makoto.core.lexicons", f"L1 claims may import only L0 lexicons: {node.module}"


# --- behavioral cases redistributed verbatim from the dissolved tests/predicates/test_helpers.py (idealization: name<->content) ---

def test_claims_done_positive():
    """positive: stop_reason=end_turn + 'done' word + no negation -> True."""
    from makoto.substrate.claims import claims_done
    payload = {"stop_reason": "end_turn", "response": "All tests pass. Phase done."}
    assert claims_done(payload) is True


def test_claims_done_rejects_non_end_turn():
    """stop_reason != end_turn -> False (don't gate non-final stops)."""
    from makoto.substrate.claims import claims_done
    payload = {"stop_reason": "tool_use", "response": "done"}
    assert claims_done(payload) is False


def test_claims_done_rejects_empty_response():
    """no response text -> False."""
    from makoto.substrate.claims import claims_done
    payload = {"stop_reason": "end_turn", "response": ""}
    assert claims_done(payload) is False


def test_claims_done_rejects_no_done_word():
    """response with no done|complete|completed|finished -> False."""
    from makoto.substrate.claims import claims_done
    payload = {"stop_reason": "end_turn", "response": "I'll work on this next."}
    assert claims_done(payload) is False


def test_claims_done_rejects_negated_claim():
    """'not done' in the 50-char window before done-word -> False."""
    from makoto.substrate.claims import claims_done
    payload = {"stop_reason": "end_turn", "response": "I am not done with this yet."}
    assert claims_done(payload) is False


def test_claims_done_rejects_contraction_negation():
    """\"isn't done\" / \"haven't finished\" caught via n't pattern."""
    from makoto.substrate.claims import claims_done
    payload = {"stop_reason": "end_turn", "response": "It isn't done yet."}
    assert claims_done(payload) is False


def test_claims_done_at_position_zero():
    """done-word at position 0 — empty negation window is handled cleanly."""
    from makoto.substrate.claims import claims_done
    payload = {"stop_reason": "end_turn", "response": "Done."}
    assert claims_done(payload) is True


def test_claims_done_ignores_negation_outside_window():
    """negation token >50 chars before done-word -> still True (window-bounded)."""
    from makoto.substrate.claims import claims_done
    # 60+ chars of neutral text starting with "not", then done-word
    response = "not at the start. " + "padding " * 10 + "All good now, done."
    payload = {"stop_reason": "end_turn", "response": response}
    assert claims_done(payload) is True


def test_claims_done_reads_real_production_field():
    """REGRESSION (2026-05-29): the REAL Claude Code Stop payload exposes the assistant
    text as `last_assistant_message` and carries NO `stop_reason`. Verified against 1759
    real captured Stop events. The gate must treat this exact shape as a done-claim —
    before the fix it always returned False (patterns 2.1/2.2/2.5 dead in production).
    """
    from makoto.substrate.claims import claims_done
    real_payload = {
        "hook_event_name": "Stop",
        "last_assistant_message": "All tests pass. Phase done.",
        # note: NO stop_reason, NO response — exactly the production shape
    }
    assert claims_done(real_payload) is True


def test_claims_done_absent_stop_reason_not_rejected():
    """absent stop_reason must NOT reject (Stop is end-of-turn by definition);
    a PRESENT non-end_turn stop_reason still rejects (covered above)."""
    from makoto.substrate.claims import claims_done
    assert claims_done({"last_assistant_message": "Done."}) is True


def test_claims_done_no_text_field_false():
    """neither last_assistant_message nor response present -> False (fail-safe)."""
    from makoto.substrate.claims import claims_done
    assert claims_done({"hook_event_name": "Stop", "session_id": "x"}) is False


def test_claims_done_real_field_negation_window():
    """negation logic applies to last_assistant_message too: 'not done' -> False."""
    from makoto.substrate.claims import claims_done
    assert claims_done({"last_assistant_message": "I am not done yet."}) is False


def test_claims_success_stop_reason_gate():
    """L319 CMP (`stop_reason != "end_turn"`): an end_turn stop with a success word
    returns a match; a non-end_turn stop (tool_use) returns None. Flipping `!=` to
    `==` inverts the gate (end_turn -> None, tool_use -> match). Pins the comparator
    in claims_success (distinct from claims_done's gate)."""
    from makoto.substrate.claims import claims_success
    assert claims_success(
        {"stop_reason": "end_turn", "response": "All done."}) is not None
    assert claims_success(
        {"stop_reason": "tool_use", "response": "All done."}) is None


def test_claims_success_negation_beyond_window_does_not_suppress():
    # lib/claims.py `len(before) > 50`: only last 50 chars before the success word scanned for
    # negation; a negation farther back must NOT suppress. The `<=` mutant widens the window
    # to the whole prefix and wrongly suppresses this real success claim.
    from makoto.substrate.claims import claims_success
    resp = "no real progress was achievable across the entire long run, task is done"
    assert claims_success(
        {"stop_reason": "end_turn", "last_assistant_message": resp}) is not None
