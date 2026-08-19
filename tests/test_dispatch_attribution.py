"""Every dispatch_errors.jsonl row names its session, its tool, and its plugin.

WHY THIS IS A TEST AND NOT A FIELD DEFAULT. audit.jsonl has carried `session_id` and `tool_name`
since 1.0.2; dispatch_errors.jsonl carried neither. So a FIRE was attributable and a MISS was not
-- and every row in this log is a check that did not run. When the question was "did that day's 30
loud-allows affect this session?", the answer was unrecoverable from the log, because the rows that
mattered were the ones built without the fields needed to answer.

The rows also name `plugin`. Ward, Gyroscope and Makoto all register PreToolUse `*` and all three
can deny, so in the shipped Courthouse configuration a row that does not name its author cannot be
attributed to one after the fact.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import _setup_state, _run_dispatch

REPO_ROOT = Path(__file__).parent.parent


def _errors(state_dir) -> list:
    f = Path(state_dir) / "dispatch_errors.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]


def _run_raw(state_dir, raw: bytes) -> tuple[int, str]:
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run([sys.executable, "-m", "makoto.dispatch"], input=raw,
                          capture_output=True, env=env, cwd=str(REPO_ROOT))
    return proc.returncode, proc.stdout.decode("utf-8")


REQUIRED = ("plugin", "session_id", "tool_name", "hook_event", "id_source")


def test_every_row_carries_the_attribution_fields(tmp_path):
    state_dir = _setup_state(tmp_path)
    _run_raw(state_dir, b'{"hook_event_name":"PreToolUse","tool_name":"Write","session_id":"s-attr",'
                        b'"cwd":"/tmp","tool_input":{"file_path":"/tmp/x.py","content":"a \x9d b"}}')
    rows = _errors(state_dir)
    assert rows, "the repair itself must be recorded"
    for row in rows:
        assert all(k in row for k in REQUIRED), f"missing attribution keys: {row}"
        assert row["plugin"] == "makoto"
        assert row["session_id"] == "s-attr"
        assert row["tool_name"] == "Write"
        assert row["hook_event"] == "PreToolUse"
        assert row["id_source"] == "payload"


def test_unparseable_stdin_still_recovers_the_ids(tmp_path):
    """The row that was unattributable BY DESIGN.

    An envelope that does not parse has no object to read ids from, which is exactly why these rows
    used to carry none. A flat scan of the raw text recovers them, and `id_source: raw-scan` says so
    -- a recovered id that does not admit it was recovered would be worse than no id at all.
    """
    state_dir = _setup_state(tmp_path)
    _run_raw(state_dir, b'{"hook_event_name":"PreToolUse","tool_name":"Bash",'
                        b'"session_id":"s-trunc","tool_input":{"comm')
    rows = [r for r in _errors(state_dir) if r["pattern_id"] == "dispatch.unparseable_payload"]
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s-trunc"
    assert rows[0]["tool_name"] == "Bash"
    assert rows[0]["id_source"] == "raw-scan"


def test_predicate_faults_are_attributed_too(tmp_path, monkeypatch):
    """A predicate that raises is the other half of this log, and it was equally anonymous."""
    from makoto.state import audit
    audit.append_error(Path(state_dir := _setup_state(tmp_path)), 7, "content.some_check",
                       ValueError("boom"), session_id="s-pred", tool_name="Edit",
                       hook_event="PreToolUse", id_source="payload")
    row = _errors(state_dir)[-1]
    assert row["session_id"] == "s-pred" and row["tool_name"] == "Edit"
    assert row["plugin"] == "makoto" and row["exc_type"] == "ValueError"


def test_pre_upgrade_rows_still_parse(tmp_path):
    """Additive, not a schema break: a row written before this change has no new keys, and the
    reader must not require them."""
    state_dir = _setup_state(tmp_path)
    log = Path(state_dir) / "dispatch_errors.jsonl"
    log.write_text(json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event_id": None,
                               "pattern_id": "dispatch.exception", "exc_type": "ValueError",
                               "exc_message": "old"}) + "\n")
    from makoto.state import audit
    rows = list(audit.read_errors(Path(state_dir)))
    assert len(rows) == 1 and rows[0].get("session_id", "") == ""


# --- the fail-open must be visible, not merely logged ----------------------------------------

def test_fail_open_emits_a_user_visible_system_message(tmp_path):
    """A loud-allow whose only "loud" is stderr is a silent one.

    Hook stderr on exit 0 goes to the debug log only -- not the transcript, not the user, not the
    model. `systemMessage` is the universal output field that IS surfaced. The fail DIRECTION is
    unchanged (still open, still exit 0); only its visibility is.
    """
    state_dir = _setup_state(tmp_path)
    code, out = _run_raw(state_dir, b'{"hook_event_name":"PreToolUse","tool_name":"Bash",'
                                    b'"session_id":"s-vis","tool_input":{"comm')
    assert code == 0
    body = json.loads(out)
    assert "ALLOWED WITHOUT BEING CHECKED" in body["systemMessage"]


def test_a_real_decision_keeps_the_wire_to_itself(tmp_path):
    """The wire carries exactly one JSON object. A notice must never be appended behind a deny."""
    state_dir = _setup_state(tmp_path)
    code, out = _run_dispatch(state_dir, {
        "hook_event_name": "PreToolUse", "tool_name": "WebFetch", "session_id": "s-deny",
        "cwd": "/tmp", "tool_input": {"url": "https://invented-host.example/v3/api"}})
    assert code == 0
    body = json.loads(out)  # would raise on a second concatenated object
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_clean_call_emits_no_notice(tmp_path):
    """No fault, no message. The channel only stays credible if it is quiet by default."""
    state_dir = _setup_state(tmp_path)
    code, out = _run_dispatch(state_dir, {
        "hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "s-quiet",
        "cwd": "/tmp", "tool_input": {"file_path": "/tmp/a"}})
    assert code == 0 and out == ""


def test_a_repaired_payload_is_not_reported_as_unchecked(tmp_path):
    """REPAIRED is not loud-allow. The call WAS checked, so no fail-open notice is emitted."""
    state_dir = _setup_state(tmp_path)
    code, out = _run_raw(state_dir, b'{"hook_event_name":"PreToolUse","tool_name":"Read",'
                                    b'"session_id":"s-rep","cwd":"/tmp",'
                                    b'"tool_input":{"file_path":"/tmp/a\x9d"}}')
    assert code == 0
    assert out == "", "a repaired-and-evaluated call must not claim it went unchecked"
