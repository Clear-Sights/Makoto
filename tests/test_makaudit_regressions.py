"""Fresh-eye regressions from MAKAUDIT.

Every defect has a precision control beside its recall/failure reproducer.  A fix that merely
turns a check off therefore cannot make this file green.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3

from makoto._dispatch import _select_recent
from makoto.checks.canonTimeoutRecur import canon_gate
from makoto.checks.claimedShippedAbsent import claimed_shipped_gate
from makoto.checks.falseGreenClaim import green_claim_gate
from makoto.checks.hollowTest import _run as hollow_test_gate
from makoto.checks.hollowTest import analyze_file as analyze_hollow_tests
from makoto.checks.namedTestTeeth import named_test_gate
from makoto.record import ledger


def _event_payload(*, command: str, response: dict) -> str:
    return json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": response,
    })


def _events_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
        "session_id TEXT NOT NULL, event_type TEXT NOT NULL, cwd TEXT NOT NULL, "
        "payload TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX events_session_ts_idx ON events(session_id, ts)")
    return conn


def _clock_regression_history(*, first_failed: bool) -> list:
    conn = _events_conn()
    now = datetime.now(timezone.utc)
    stamps = (
        now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        (now - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )
    responses = (
        {"error": "first failed"} if first_failed else {"stdout": "first succeeded"},
        {"stdout": "second succeeded"} if first_failed else {"error": "second failed"},
    )
    for stamp, response in zip(stamps, responses):
        conn.execute(
            "INSERT INTO events (ts, session_id, event_type, cwd, payload) "
            "VALUES (?, 's', 'PostToolUse', '/repo', ?)",
            [stamp, _event_payload(command="same-call", response=response)],
        )
    try:
        return _select_recent(conn, "s", 3)
    finally:
        conn.close()


def test_fp_stop_history_uses_ingest_order_when_wall_clock_moves_backward(tmp_path):
    history = _clock_regression_history(first_failed=True)
    assert canon_gate(history, state_root=tmp_path) == []


def test_tp_stop_history_keeps_later_error_last_when_clock_moves_backward(tmp_path):
    history = _clock_regression_history(first_failed=False)
    findings = canon_gate(history, state_root=tmp_path)
    assert any(f.message.startswith("canon.timeout:") for f in findings)


def _ledger_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute(
        "CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
        "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)"
    )
    return conn


def _record_test_run(conn, *, session_id: str, event_id: int, command: str, output: str,
                     exit_code: int) -> None:
    ledger.record_update(
        conn,
        {
            "tool_name": "Bash",
            "cwd": "/repo",
            "tool_input": {"command": command},
            "tool_response": {"stdout": output, "exitCode": exit_code},
        },
        event_id=event_id,
        session_id=session_id,
    )


def test_fp_cross_session_upsert_never_attributes_second_sessions_failure_to_first():
    conn = _ledger_conn()
    _record_test_run(
        conn, session_id="first", event_id=1, command="pytest -q",
        output="1 passed", exit_code=0,
    )
    _record_test_run(
        conn, session_id="second", event_id=2, command="pytest -q",
        output="1 failed", exit_code=1,
    )
    first_output = ledger.latest_testrun(conn, "first")
    assert green_claim_gate("All tests pass.", testrun_output=first_output) is None


def test_tp_cross_session_upsert_attributes_failure_to_session_that_ran_it():
    conn = _ledger_conn()
    _record_test_run(
        conn, session_id="first", event_id=1, command="pytest -q",
        output="1 passed", exit_code=0,
    )
    _record_test_run(
        conn, session_id="second", event_id=2, command="pytest -q",
        output="1 failed", exit_code=1,
    )
    second_output = ledger.latest_testrun(conn, "second")
    assert green_claim_gate("All tests pass.", testrun_output=second_output) is not None


def _history_row(payload) -> dict:
    return {"payload": json.dumps(payload)}


def test_fp_non_object_history_payload_is_inert_for_named_test_gate():
    malformed = _history_row(["valid JSON", "wrong envelope shape"])
    assert named_test_gate("test_widget passes.", history=[malformed]) is None


def test_tp_non_object_history_payload_does_not_hide_later_failed_named_test():
    malformed = _history_row(["valid JSON", "wrong envelope shape"])
    failed = _history_row({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "pytest -q tests/test_widget.py::test_widget"},
        "tool_response": {
            "stdout": "FAILED tests/test_widget.py::test_widget - AssertionError",
            "exitCode": 1,
        },
    })
    finding = named_test_gate("test_widget passes.", history=[malformed, failed])
    assert finding is not None
    assert finding.pattern_id == "gate.named_test"


def test_fp_green_claim_ignores_failure_text_read_from_pytest_log():
    conn = _ledger_conn()
    _record_test_run(
        conn, session_id="reader", event_id=1, command="cat pytest.log",
        output="2 failed", exit_code=0,
    )
    output = ledger.latest_testrun(conn, "reader")
    assert green_claim_gate("All tests pass.", testrun_output=output) is None


def test_tp_green_claim_still_blocks_after_real_pytest_failure():
    conn = _ledger_conn()
    _record_test_run(
        conn, session_id="runner", event_id=1, command="pytest -q",
        output="2 failed", exit_code=1,
    )
    output = ledger.latest_testrun(conn, "runner")
    assert green_claim_gate("All tests pass.", testrun_output=output) is not None


def _bash_history(command: str) -> list:
    return [_history_row({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": "ok", "exitCode": 0},
    })]


def test_not_evaluable_echoed_git_push_is_not_remote_evidence():
    assert claimed_shipped_gate(
        "I've pushed it to main.",
        history=_bash_history("echo 'git push origin main'"),
    ) is None


def test_fp_real_git_push_still_discharges_claimed_shipped():
    assert claimed_shipped_gate(
        "I've pushed it to main.",
        history=_bash_history("git -C /repo push origin main"),
    ) is None


_INTENTIONAL_HOLLOW = (
    "def test_validate_predicate_modules_passes_on_current_catalog():  "
    "# makoto-allow: success is defined as not raising\n"
    "    validate()\n"
)


def test_fp_intentional_hollow_allow_remains_silent_in_live_adapter(tmp_path):
    path = tmp_path / "test_install.py"
    path.write_text(_INTENTIONAL_HOLLOW, encoding="utf-8")

    class Context:
        touched = frozenset({str(path)})

        @staticmethod
        def fs_read(_path):
            return _INTENTIONAL_HOLLOW

    assert hollow_test_gate(Context()) == []


def test_tp_intentional_hollow_remains_detectable_before_exemption():
    findings = analyze_hollow_tests(_INTENTIONAL_HOLLOW, "test_install.py")
    assert any(
        f["func"] == "test_validate_predicate_modules_passes_on_current_catalog"
        and f["kind"] == "no_assertion"
        for f in findings
    )
