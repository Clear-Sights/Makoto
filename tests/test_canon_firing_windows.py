"""A recorded fingerprint firing closes only that fingerprint's occurrence window."""
from dataclasses import asdict
from pathlib import Path

import pytest

from makoto.checks.canonFingerprints import canon_fingerprint_block_gate
from makoto.state import audit, ledger
from tests.test_canon_atom_window import T0, T1, T2, _green, _operator, _row, _timeout, _transcript

GATE = "gate.canon_fingerprints"


def _fire(history, root, transcript_path=None, session_id="s1"):
    return canon_fingerprint_block_gate(
        "", history, transcript_path=transcript_path, session_id=session_id, state_root=root)


def _record(root, findings, ts=T1, session_id="s1"):
    audit.append_row(root, audit.AuditRow(
        ts=ts, event="Stop", hook_kind="Stop", session_id=session_id, project_root="/w",
        pattern_fires=sorted({f.pattern_id for f in findings}), exit_code=2,
        retry_hint_emitted=True, findings=[asdict(f) for f in findings]))


def test_audited_stop_clears_then_recurrence_blocks_and_clears_again(tmp_path):
    history = [_green(T0), _timeout(T0)]
    first = _fire(history, tmp_path)
    assert len(first) == 1
    assert first[0].message.startswith("canon.nosrc_green_timeout:")
    assert first[0].level == "error"
    assert "re-examine; a new call window starts at this firing; repeating the pattern re-blocks" \
        in first[0].retry_hint.lower()
    _record(tmp_path, first)
    before = ledger.read(root=tmp_path)
    assert before[0]["kind"] == "audit"
    assert _fire(history, tmp_path) == []
    assert _fire(history + [_green(T1), _timeout(T1)], tmp_path) == []
    assert _fire(history + [_green(T2)], tmp_path) == [], "old timeout cannot join new green"
    repeated = history + [_green(T2), _timeout(T2)]
    second = _fire(repeated, tmp_path)
    assert len(second) == 1 and second[0].level == "error"
    _record(tmp_path, second, ts=T2)
    assert _fire(repeated, tmp_path) == []
    assert ledger.read(root=tmp_path)[:1] == before, "existing audit rows stay unchanged"
    assert ledger.verify_chain(root=tmp_path) is None


def test_each_fingerprint_uses_its_own_window(tmp_path):
    history = [_row(T0, "Bash", {"command": "rm -rf build/"})]
    first = _fire(history, tmp_path)
    assert len(first) == 2
    target = next(f for f in first if f.message.startswith("canon.notestedit_destruct:"))
    _record(tmp_path, [target])
    remaining = _fire(history, tmp_path)
    assert len(remaining) == 1
    assert remaining[0].message.startswith("canon.nosrc_destruct:")


def test_new_operator_boundary_is_later_than_last_firing(tmp_path):
    first = _fire([_green(T0), _timeout(T0)], tmp_path)
    _record(tmp_path, first, ts=T0)
    history = [_green(T1), _timeout(T1)]
    assert _fire(history, tmp_path)
    path = _transcript(tmp_path, [_operator("continue", T2)])
    assert _fire(history, tmp_path, path) == []


def test_firing_boundary_is_later_than_operator_boundary(tmp_path):
    path = _transcript(tmp_path, [_operator("continue", T0)])
    history = [_green(T1), _timeout(T1)]
    first = _fire(history, tmp_path, path)
    _record(tmp_path, first, ts=T2)
    assert _fire(history, tmp_path, path) == []


def test_other_sessions_firing_does_not_close_this_window(tmp_path):
    history = [_green(T0), _timeout(T0)]
    _record(tmp_path, _fire(history, tmp_path), session_id="other")
    assert _fire(history, tmp_path)
    assert _fire(history, tmp_path, session_id=None)


def _audit_row(ts, **overrides):
    return {"kind": "audit", "session_id": "s1", "ts": ts,
            "pattern_fires": [GATE],
            "findings": [{"message": "canon.nosrc_green_timeout: fired"}], **overrides}


def test_last_fired_ts_selects_latest_instant_not_first_or_string_order(tmp_path):
    assert ledger.last_fired_ts("nosrc_green_timeout", session_id="s1", root=tmp_path) is None
    for ts in (T0, T2, "2026-09-08T14:00:00+03:00", "invalid"):
        ledger.append(_audit_row(ts), root=tmp_path)
    assert ledger.last_fired_ts("nosrc_green_timeout", session_id="s1", root=tmp_path) == T2


@pytest.mark.parametrize("overrides", [
    {"kind": "exemption"}, {"session_id": "other"}, {"pattern_fires": ["gate.canon"]},
    {"findings": [{"message": "canon.nosrc_destruct: fired"}]},
    {"findings": [{"message": "canon.nosrc_green_timeout_extra: fired"}]},
])
def test_last_fired_ts_ignores_unrelated_rows(tmp_path, overrides):
    ledger.append(_audit_row(T1, **overrides), root=tmp_path)
    assert ledger.last_fired_ts("nosrc_green_timeout", session_id="s1", root=tmp_path) is None


def test_equal_instants_with_different_offsets_are_outside_window(tmp_path):
    history = [_green(T0), _timeout(T0)]
    _record(tmp_path, _fire(history, tmp_path), ts=T1)
    assert _fire([_green("2026-09-08T13:00:00+02:00"), _timeout(T1)], tmp_path) == []


def test_dispatch_records_firing_and_next_stop_does_not_repeat(state_dir, run_dispatch):
    payload = {"session_id": "firing-window", "cwd": "/tmp"}
    call = {**payload, "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": "rm -rf build/"}, "tool_response": {"exitCode": 0}}
    stop = {**payload, "hook_event_name": "Stop", "last_assistant_message": ""}
    run_dispatch(state_dir, call)
    _, first = run_dispatch(state_dir, stop)
    assert '"decision": "block"' in first
    assert "canon.nosrc_destruct:" in first
    rows = [r for r in ledger.read(root=state_dir)
            if r.get("kind") == "audit" and GATE in r.get("pattern_fires", [])]
    assert len(rows) == 1
    assert rows[0]["retry_hint_emitted"] is True
    assert rows[0]["exit_code"] == 2
    _, second = run_dispatch(state_dir, stop)
    assert GATE not in second
    run_dispatch(state_dir, call)
    _, third = run_dispatch(state_dir, stop)
    assert '"decision": "block"' in third
    assert "canon.nosrc_destruct:" in third
    _, fourth = run_dispatch(state_dir, stop)
    assert "canon.nosrc_destruct:" not in fourth
    assert ledger.verify_chain(root=state_dir) is None


def test_retired_human_phrase_is_absent_from_tree_except_history():
    # Scan every source (including multiline or dynamically constructed hint templates).
    root = Path(__file__).resolve().parents[1]
    phrase = "release" + ".operator"
    for path in root.rglob("*"):
        if set(path.relative_to(root).parts) & {".git", "__pycache__", ".pytest_cache"}:
            continue
        if not path.is_file() or path.name == "CHANGELOG.md":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        assert phrase not in source, str(path.relative_to(root))
