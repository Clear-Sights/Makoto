"""Claude Code's context-COMPACTION summary arrives as a SubagentStop whose payload carries an
empty ``agent_type`` and no (or an empty) ``agent_id``. Its ``last_assistant_message`` summarizes
earlier work; it is not a claim of this turn, so no claim-reading Stop gate may read it. A real
subagent's SubagentStop (non-empty agent_type, agent_id set) is checked exactly as before."""
import json

from tests.conftest import _setup_state, _run_dispatch

SUMMARY = ("Summary of the work so far: I created _declared.py. "
           "I ran `pytest tests/zzz_unrun.py -q` and it all passed.")


def _gate_ids(state_dir):
    audit = state_dir / "audit.jsonl"
    if not audit.exists():
        return set()
    ids = set()
    for line in audit.read_text().splitlines():
        if line.strip():
            ids.update(json.loads(line).get("pattern_fires") or ())
    return ids


def test_compaction_stop_no_agent_id_runs_no_claim_gates(tmp_path):
    # discriminant: agent_type key present but "", agent_id key absent -- the compaction shape
    state_dir = _setup_state(tmp_path)
    payload = {"hook_event_name": "SubagentStop", "session_id": "compact_a", "cwd": str(tmp_path),
               "agent_type": "", "last_assistant_message": SUMMARY}
    rc, out = _run_dispatch(state_dir, payload)
    assert out == "", f"compaction summary must not be gated as a claim; got {out!r}"
    fired = _gate_ids(state_dir)
    assert "gate.completion" not in fired and "gate.fabricated_action" not in fired, fired


def test_compaction_stop_empty_agent_id_runs_no_claim_gates(tmp_path):
    # discriminant: agent_id key present but "" alongside agent_type "" -- compaction's other variant
    state_dir = _setup_state(tmp_path)
    payload = {"hook_event_name": "SubagentStop", "session_id": "compact_b", "cwd": str(tmp_path),
               "agent_id": "", "agent_type": "", "last_assistant_message": SUMMARY}
    rc, out = _run_dispatch(state_dir, payload)
    assert out == "", f"compaction summary must not be gated as a claim; got {out!r}"
    fired = _gate_ids(state_dir)
    assert "gate.completion" not in fired and "gate.fabricated_action" not in fired, fired


def test_real_subagent_stop_same_summary_still_blocks(tmp_path):
    # discriminant: agent_type "general-purpose" and agent_id set -- a real subagent's own claim
    state_dir = _setup_state(tmp_path)
    payload = {"hook_event_name": "SubagentStop", "session_id": "compact_c", "cwd": str(tmp_path),
               "agent_id": "a1b2c3", "agent_type": "general-purpose",
               "last_assistant_message": SUMMARY}
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "a real subagent claiming an unmade file and an unrun command must still block"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    fired = _gate_ids(state_dir)
    assert "gate.fabricated_action" in fired and "gate.completion" in fired, fired
