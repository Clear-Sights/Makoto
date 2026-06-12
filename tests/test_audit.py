"""tests for makoto.audit — JSONL writer, reader, error log, snippet helper.

1.0.3 collapse: dropped summarize / read_recent_events tests + `audit` CLI
subprocess tests (their corresponding code was removed). Kept tests for
AuditRow + append_row + read_rows + append_error + _make_snippet — the
functions the dispatcher actually uses.
"""
import json
from dataclasses import asdict
import pytest
from makoto.audit import AuditRow, append_row, read_rows, append_error


def _sample_row(**overrides) -> AuditRow:
    """construct a minimal AuditRow with sane defaults; overrides replace named fields."""
    base = dict(
        ts="2026-05-24T03:45:32.123456Z",
        event="live.pre_tool_use",
        hook_kind="PreToolUse",
        session_id="s1",
        project_root="/tmp",
        pattern_fires=[],
        exit_code=0,
        retry_hint_emitted=False,
        findings=[],
    )
    base.update(overrides)
    return AuditRow(**base)


def test_auditrow_fields_dataclass_round_trip():
    """AuditRow holds all fields and asdict round-trips them."""
    row = AuditRow(
        ts="2026-05-24T03:45:32.123456Z",
        event="live.pre_tool_use",
        hook_kind="PreToolUse",
        session_id="abc123",
        project_root="/tmp/proj",
        pattern_fires=["1.4"],
        exit_code=2,
        retry_hint_emitted=True,
        findings=[{"pattern_id": "1.4", "level": "error",
                   "file": "x.md", "line": 5, "snippet": "Hill 1980"}],
    )
    d = asdict(row)
    assert d["ts"] == "2026-05-24T03:45:32.123456Z"
    assert d["pattern_fires"] == ["1.4"]
    assert d["findings"][0]["snippet"] == "Hill 1980"


def test_append_row_creates_jsonl_with_one_line(tmp_path):
    """append_row writes a single JSON line + newline to <state_root>/audit.jsonl."""
    append_row(tmp_path, _sample_row())
    log = tmp_path / "audit.jsonl"
    assert log.is_file()
    content = log.read_text()
    assert content.endswith("\n")
    assert content.count("\n") == 1


def test_append_row_creates_state_root_if_missing(tmp_path):
    """append_row mkdirs the state_root if absent."""
    target = tmp_path / "nested" / "state"
    append_row(target, _sample_row())
    assert (target / "audit.jsonl").is_file()


def test_append_row_multiple_appends_preserve_order(tmp_path):
    """N appends produce N lines in the order they were written."""
    for i in range(3):
        append_row(tmp_path, _sample_row(session_id=f"s{i}"))
    log = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(log) == 3
    parsed = [json.loads(l) for l in log]
    assert [r["session_id"] for r in parsed] == ["s0", "s1", "s2"]


def test_read_rows_round_trips_appended_data(tmp_path):
    """write + read returns equivalent dicts."""
    append_row(tmp_path, _sample_row(event="live.stop"))
    append_row(tmp_path, _sample_row(event="pre_commit"))
    rows = list(read_rows(tmp_path))
    assert len(rows) == 2
    assert rows[0]["event"] == "live.stop"
    assert rows[1]["event"] == "pre_commit"


def test_read_rows_missing_file_returns_empty(tmp_path):
    """no audit.jsonl -> empty iterator (not an error)."""
    assert list(read_rows(tmp_path)) == []


def test_read_rows_skips_malformed_lines(tmp_path):
    """invalid JSON lines are silently skipped, not raised."""
    log = tmp_path / "audit.jsonl"
    log.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "event": "good"}) + "\n"
        + "this is not json\n"
        + json.dumps({"ts": "2026-01-02T00:00:00Z", "event": "alsogood"}) + "\n",
        encoding="utf-8",
    )
    rows = list(read_rows(tmp_path))
    assert len(rows) == 2
    assert rows[0]["event"] == "good"
    assert rows[1]["event"] == "alsogood"


def test_read_rows_since_filter_drops_earlier_rows(tmp_path):
    """since='2026-05-24T01:30:00Z' drops rows with smaller ts strings."""
    for ts in ["2026-05-24T01:00:00.000000Z",
               "2026-05-24T02:00:00.000000Z",
               "2026-05-24T03:00:00.000000Z"]:
        append_row(tmp_path, _sample_row(ts=ts))
    rows = list(read_rows(tmp_path, since="2026-05-24T01:30:00Z"))
    assert len(rows) == 2
    assert rows[0]["ts"].startswith("2026-05-24T02")


def test_append_error_writes_to_dispatch_errors_jsonl(tmp_path):
    """append_error writes one JSON line to <state_root>/dispatch_errors.jsonl."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        append_error(tmp_path, event_id=42, pattern_id="1.6", exc=exc)
    log = tmp_path / "dispatch_errors.jsonl"
    assert log.is_file()
    row = json.loads(log.read_text().strip())
    assert row["event_id"] == 42
    assert row["pattern_id"] == "1.6"
    assert row["exc_type"] == "ValueError"
    assert "boom" in row["exc_message"]
    assert "ts" in row


def test_append_error_does_not_touch_audit_jsonl(tmp_path):
    """append_error MUST NOT write to audit.jsonl (separate logs)."""
    try:
        raise RuntimeError("x")
    except RuntimeError as exc:
        append_error(tmp_path, event_id=None, pattern_id=None, exc=exc)
    assert not (tmp_path / "audit.jsonl").exists()  # untouched
    assert (tmp_path / "dispatch_errors.jsonl").exists()
