"""SPEC-5 Task 8 integration pins: the posture cutover (`dispatch._emit_decision` now folds a
fired finding through `makoto.verdict`'s posture fold + wire tables instead of the old single ad-hoc
"decision":"block" shape). Three behavioral claims, one test each:

  1. a BLOCK precheck (PreToolUse) denies via the NEW nested Pre shape.
  2. a BLOCK Stop gate still blocks via the OLD top-level "decision":"block" shape (wire.py's
     Stop table renders that shape by construction -- this is deliberately unchanged).
  3. PostToolUse still runs refresh_if_stale/record_update with `citations.capture()` removed
     (no capture-shaped effect: a research-tool response's citations never land in
     canonical_citations, but the ledger `update` row and citations refresh still happen).
"""
import json
import sqlite3

from tests.conftest import _setup_state, _run_dispatch


def test_pretooluse_block_renders_new_wire_shape(tmp_path):
    """PreCheck content.verifier_predicate_weakened (loose comparator) fires on PreToolUse -> the real Pre wire shape
    (hookSpecificOutput.permissionDecision == "deny"), not the old top-level "decision" key."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "posture_pre",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "constitution/integrity/checks/v.py",
            "content": 'def check(x):\n    return x.startswith("ok")\n',
        },
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert rc == 0
    assert out, "expected a deny body on stdout"
    body = json.loads(out)
    assert "decision" not in body, "Pre must not use the old ad-hoc top-level shape"
    assert body["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stop_gate_block_still_uses_old_top_level_shape(tmp_path):
    """gate.completion (a Stop gate) still renders {"decision": "block", ...} -- wire.py's
    Stop/SubagentStop table renders exactly that shape for a BLOCK outcome, so this is a
    no-op cutover for every existing Stop gate."""
    state_dir = _setup_state(tmp_path)
    stop = {
        "hook_event_name": "Stop",
        "session_id": "posture_stop",
        "cwd": str(tmp_path),
        "last_assistant_message": "Created src/promised_zzz.py. Done.",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "expected a block body on stdout"
    body = json.loads(out)
    assert body["decision"] == "block"
    assert body["hookEventName"] == "Stop"
    assert "src/promised_zzz.py" in body["reason"]


def test_posttooluse_still_refreshes_and_records_without_capture(tmp_path):
    """PostToolUse must still run refresh_if_stale (a canonical_citations row from CITATIONS.md
    exists) and record_update (a Write lands a ledger row), but a research-class tool's response
    (WebFetch) must NEVER seed canonical_citations now that capture() is gone."""
    state_dir = _setup_state(tmp_path)
    write = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "posture_post",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "src/x.py", "content": "pass\n"},
        "tool_response": {},
    }
    webfetch = {
        "hook_event_name": "PostToolUse",
        "tool_name": "WebFetch",
        "session_id": "posture_post",
        "cwd": str(tmp_path),
        "tool_input": {"url": "https://example.com"},
        "tool_response": "See Doe 2031 for details.",
    }
    rc1, out1 = _run_dispatch(state_dir, write)
    rc2, out2 = _run_dispatch(state_dir, webfetch)
    assert (rc1, out1) == (0, "")
    assert (rc2, out2) == (0, "")
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    try:
        cites = [r[0] for r in conn.execute("SELECT cite FROM canonical_citations").fetchall()]
        assert "Doe 2031" not in cites, (
            "capture() is removed -- a research tool_response must never seed canonical_citations"
        )
        assert cites, "refresh_if_stale must still have loaded CITATIONS.md's own citation(s)"
        ledger_rows = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        assert ledger_rows > 0, "record_update must still run on PostToolUse"
    finally:
        conn.close()


# --- meta-layer immunity (Check.layer wired into the fold, claude/port-layer-immunity) ----------
# A layer="meta" check's ONLY possible trigger is tampering with Makoto's own audit/enforcement
# machinery, so LOOSE/SILENT must not be able to soften its BLOCK below ASK -- the posture knob
# is itself part of the machinery a meta check guards. Object-layer folds are byte-identical.

import io

from makoto import dispatch, verdict
from makoto.vocab import Finding


def _block_finding(pattern_id):
    return Finding(pattern_id=pattern_id, file="settings.json", line=1, level="error",
                   message=f"{pattern_id} fired", source_event_id=1)


def _emit(finding, mode, monkeypatch, permission_mode=None):
    monkeypatch.setenv("MAKOTO_MODE", mode)
    stream = io.StringIO()
    dispatch._emit_decision([finding], "PreToolUse", stream=stream,
                            permission_mode=permission_mode)
    return stream.getvalue()


def test_apply_meta_block_floors_at_ask_under_loose_and_silent():
    """The pure fold: a meta BLOCK never softens below ASK; every other (outcome, layer) cell of
    the fold table is unchanged from the object-layer rules."""
    assert verdict.apply(verdict.BLOCK, verdict.LOOSE, layer="meta") == verdict.ASK
    assert verdict.apply(verdict.BLOCK, verdict.SILENT, layer="meta") == verdict.ASK
    # STRICT / ASK postures already sit at or above the floor -- unchanged.
    assert verdict.apply(verdict.BLOCK, verdict.STRICT, layer="meta") == verdict.BLOCK
    assert verdict.apply(verdict.BLOCK, verdict.ASK_POSTURE, layer="meta") == verdict.ASK
    # The contract is exactly "a meta BLOCK never softens below ASK" -- a meta ASK/ADVISE/ALLOW
    # folds by the ordinary rules (SILENT still suppresses them).
    assert verdict.apply(verdict.ASK, verdict.SILENT, layer="meta") == verdict.ALLOW
    assert verdict.apply(verdict.ADVISE, verdict.LOOSE, layer="meta") == verdict.ADVISE
    assert verdict.apply(verdict.ALLOW, verdict.SILENT, layer="meta") == verdict.ALLOW
    # Object layer (and the default, i.e. every existing caller): byte-identical old behavior.
    assert verdict.apply(verdict.BLOCK, verdict.LOOSE) == verdict.ADVISE
    assert verdict.apply(verdict.BLOCK, verdict.SILENT) == verdict.ALLOW
    assert verdict.apply(verdict.BLOCK, verdict.LOOSE, layer="object") == verdict.ADVISE
    # D6 oversight clamp outranks the floor question entirely: raw BLOCK either way.
    assert verdict.apply(verdict.BLOCK, verdict.LOOSE, layer="meta",
                         permission_mode="bypassPermissions") == verdict.BLOCK


def test_meta_check_ids_derived_not_hand_synced():
    """_meta_check_ids is DERIVED from the catalog's layer tags -- exactly the two known-meta
    checks today (same source of truth tests/test_meta_layer.py pins)."""
    assert dispatch._meta_check_ids() == frozenset({"content.self_mute_guard",
                                                    "gate.self_wired"})


def test_meta_block_finding_floors_at_ask_on_the_wire(monkeypatch):
    """RED under the pre-wiring code (LOOSE softened a self_mute_guard BLOCK to an allow+context
    advisory; SILENT swallowed it entirely): a BLOCK-level finding from the meta-layer
    content.self_mute_guard check renders the Pre 'ask' wire shape under BOTH softening
    postures -- detection of tampering with Makoto's own kill-switches survives a permissive
    MAKOTO_MODE."""
    meta = _block_finding("content.self_mute_guard")
    for mode in ("loose", "silent"):
        out = _emit(meta, mode, monkeypatch)
        assert out, f"meta BLOCK must not be suppressed under {mode}"
        body = json.loads(out)
        assert body["hookSpecificOutput"]["permissionDecision"] == "ask", (
            f"meta BLOCK must floor at ASK under {mode}, got {body}")


def test_object_block_finding_still_folds_normally(monkeypatch):
    """Control: an object-layer BLOCK finding keeps the exact old fold -- LOOSE softens it to an
    allow+context advisory, SILENT writes nothing at all."""
    obj = _block_finding("content.verifier_predicate_weakened")
    loose = json.loads(_emit(obj, "loose", monkeypatch))
    assert "additionalContext" in loose["hookSpecificOutput"], "LOOSE object BLOCK -> ADVISE"
    assert loose["hookSpecificOutput"].get("permissionDecision") != "ask"
    assert _emit(obj, "silent", monkeypatch) == "", "object BLOCK under SILENT stays suppressed"


def test_meta_floor_recheck_certificate_agrees(monkeypatch):
    """F4 consistency: with MAKOTO_RECHECK_CERTIFICATE=1 the certificate reconstruction folds
    the meta floor identically (a mismatch would raise inside _emit_decision)."""
    monkeypatch.setenv("MAKOTO_RECHECK_CERTIFICATE", "1")
    out = _emit(_block_finding("content.self_mute_guard"), "loose", monkeypatch)
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "ask"
