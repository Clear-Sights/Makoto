"""Tests for makoto.posture + makoto.wire — the ported enforcement-posture skeleton (SPEC-5 Task 1).

Falsifier: python -m pytest makoto/tests/test_posture_wire.py -q

Asserts the posture-fold (``posture.apply``) and the per-edge wire rendering (``wire.dispatch_posture``)
match Assay's source shape (``assay/assay/runtime/mode.py`` + ``assay/assay/adapters/hook_bridge.py``):
  * BLOCK at Pre -> ``permissionDecision: "deny"`` (nested under ``hookSpecificOutput``).
  * BLOCK at Stop/SubagentStop -> ``decision: "block"``, echoing the firing hook name.
  * ASK at Pre -> ``permissionDecision: "ask"``.
  * ADVISE -> allow + ``additionalContext`` present, NEVER a deny/ask/block key.
  * ALLOW -> ``{}`` on every edge.
  * Post edge NEVER emits anything but ADVISE -> ``additionalContext`` or ``{}`` — BLOCK/ASK/ALLOW
    at Post must all render ``{}``, never a deny/block key.
"""

from __future__ import annotations

from makoto import posture
from makoto.wire import dispatch_posture

_ALL_POSTURES = (posture.BLOCK, posture.ASK, posture.ADVISE, posture.ALLOW)


# --- posture.apply fold (mirrors mode.py's fold table) -------------------------------------------


def test_apply_strict_honors_raw_outcome():
    for outcome in _ALL_POSTURES:
        assert posture.apply(outcome, posture.STRICT) == outcome


def test_apply_silent_forces_allow_always():
    for outcome in _ALL_POSTURES:
        assert posture.apply(outcome, posture.SILENT) == posture.ALLOW


def test_apply_loose_softens_block_to_advise():
    assert posture.apply(posture.BLOCK, posture.LOOSE) == posture.ADVISE
    assert posture.apply(posture.ASK, posture.LOOSE) == posture.ASK
    assert posture.apply(posture.ADVISE, posture.LOOSE) == posture.ADVISE
    assert posture.apply(posture.ALLOW, posture.LOOSE) == posture.ALLOW


def test_apply_ask_posture_escalates_block_and_ask():
    assert posture.apply(posture.BLOCK, posture.ASK_POSTURE) == posture.ASK
    assert posture.apply(posture.ASK, posture.ASK_POSTURE) == posture.ASK
    assert posture.apply(posture.ADVISE, posture.ASK_POSTURE) == posture.ADVISE
    assert posture.apply(posture.ALLOW, posture.ASK_POSTURE) == posture.ALLOW


def test_apply_allow_is_a_fixpoint_under_every_posture():
    for posture_value in (posture.LOOSE, posture.STRICT, posture.ASK_POSTURE, posture.SILENT):
        assert posture.apply(posture.ALLOW, posture_value) == posture.ALLOW


def test_apply_unrecognized_posture_fails_closed_to_strict():
    assert posture.apply(posture.BLOCK, "not-a-real-posture") == posture.BLOCK


# ---- D6: permission_mode-aware clamp (FABLE DECISION 2026-07-07) -----------------------------
def test_is_oversight_clamped_true_for_bypasspermissions_and_dontask():
    assert posture.is_oversight_clamped("bypassPermissions") is True
    assert posture.is_oversight_clamped("dontAsk") is True


def test_is_oversight_clamped_false_for_every_other_mode_incl_none():
    for mode in ("default", "plan", "acceptEdits", "auto", None, "", "garbage"):
        assert posture.is_oversight_clamped(mode) is False


def test_apply_clamps_loose_block_to_block_under_bypasspermissions():
    """The whole point of D6: LOOSE would normally soften a BLOCK to ADVISE -- forced back to
    BLOCK when the harness's own human-confirmation layer is off."""
    assert posture.apply(posture.BLOCK, posture.LOOSE,
                         permission_mode="bypassPermissions") == posture.BLOCK


def test_apply_clamps_silent_block_to_block_under_dontask():
    assert posture.apply(posture.BLOCK, posture.SILENT,
                         permission_mode="dontAsk") == posture.BLOCK


def test_apply_clamps_ask_ask_to_ask_unchanged_under_bypasspermissions():
    """ASK escalates BLOCK/ASK to ASK anyway -- the clamp forces the RAW outcome through, which
    for an ASK-postured BLOCK means BLOCK (stricter than ASK's own escalation), not ASK."""
    assert posture.apply(posture.BLOCK, posture.ASK_POSTURE,
                         permission_mode="bypassPermissions") == posture.BLOCK


def test_apply_clamp_never_escalates_allow():
    """ALLOW stays a fixpoint even under the clamp -- the clamp only stops SOFTENING a real
    flag, it never manufactures one, matching apply's own no-escalation contract for ALLOW."""
    assert posture.apply(posture.ALLOW, posture.LOOSE,
                         permission_mode="bypassPermissions") == posture.ALLOW


def test_apply_unclamped_modes_behave_exactly_as_before():
    """default/plan/acceptEdits/auto/None must not trigger the clamp -- LOOSE still softens."""
    for mode in ("default", "plan", "acceptEdits", "auto", None):
        assert posture.apply(posture.BLOCK, posture.LOOSE,
                             permission_mode=mode) == posture.ADVISE


def test_decision_carries_detail_but_compares_as_its_outcome_string():
    d = posture.Decision(posture.BLOCK, detail="/etc/passwd")
    assert d == posture.BLOCK
    assert d.detail == "/etc/passwd"


# --- Pre edge --------------------------------------------------------------------------------


def test_pre_block_denies_with_permission_decision_key():
    body = dispatch_posture("Pre", posture.BLOCK, "PreToolUse")
    hso = body["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "permissionDecisionReason" in hso
    assert "additionalContext" not in hso


def test_pre_ask_is_ask_shaped():
    body = dispatch_posture("Pre", posture.ASK, "PreToolUse")
    hso = body["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask"
    assert "permissionDecisionReason" in hso


def test_pre_advise_allows_and_injects_context_never_denies():
    body = dispatch_posture("Pre", posture.ADVISE, "PreToolUse")
    hso = body["hookSpecificOutput"]
    assert "additionalContext" in hso
    assert "permissionDecision" not in hso


def test_pre_allow_is_empty():
    assert dispatch_posture("Pre", posture.ALLOW, "PreToolUse") == {}


def test_pre_block_detail_overrides_constant_reason():
    d = posture.Decision(posture.BLOCK, detail="/etc/shadow is forbidden")
    body = dispatch_posture("Pre", d, "PreToolUse")
    assert "/etc/shadow is forbidden" in body["hookSpecificOutput"]["permissionDecisionReason"]


# --- Stop / SubagentStop edges ------------------------------------------------------------------


def test_stop_block_blocks_the_stop():
    body = dispatch_posture("Stop", posture.BLOCK, "Stop")
    assert body["decision"] == "block"
    assert body["hookEventName"] == "Stop"
    assert "reason" in body


def test_subagent_stop_block_echoes_subagent_stop_hook_name():
    body = dispatch_posture("SubagentStop", posture.BLOCK, "SubagentStop")
    assert body["decision"] == "block"
    assert body["hookEventName"] == "SubagentStop"


def test_stop_non_block_postures_never_block():
    for outcome in (posture.ASK, posture.ADVISE, posture.ALLOW):
        assert dispatch_posture("Stop", outcome, "Stop") == {}
        assert dispatch_posture("SubagentStop", outcome, "SubagentStop") == {}


# --- Post edge: structurally can never deny/block, only ADVISE or {} ----------------------------


def test_post_advise_allows_and_injects_context():
    body = dispatch_posture("Post", posture.ADVISE, "PostToolUse")
    hso = body["hookSpecificOutput"]
    assert "additionalContext" in hso
    assert "permissionDecision" not in hso
    assert "decision" not in body


def test_post_never_emits_anything_but_advise_or_empty():
    for outcome in _ALL_POSTURES:
        body = dispatch_posture("Post", outcome, "PostToolUse")
        if outcome == posture.ADVISE:
            assert "additionalContext" in body["hookSpecificOutput"]
        else:
            assert body == {}
        # Regardless of outcome, Post must never carry a deny/block key.
        assert "decision" not in body
        if "hookSpecificOutput" in body:
            assert "permissionDecision" not in body["hookSpecificOutput"]


def test_dispatch_posture_unrecognized_edge_fails_open_to_empty():
    assert dispatch_posture("NotAnEdge", posture.BLOCK, "NotAnEdge") == {}
