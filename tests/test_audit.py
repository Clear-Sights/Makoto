"""tests for makoto.state.audit — JSONL writer, error log, snippet helper.

1.0.3 collapse: dropped summarize / read_recent_events tests + `audit` CLI
subprocess tests (their corresponding code was removed). Kept tests for
AuditRow + append_row + append_error + _make_snippet — the functions the
dispatcher actually uses. The log is write-only in production (no plugin
reader), so `read_rows`/`_read_jsonl` were removed with the rest of the
dead reader surface (state/audit.py); a round-trip check here reads the
jsonl file directly instead.
"""
import json
import pytest
from makoto.state.audit import AuditRow, append_row, append_error


def _read_jsonl(path):
    """Local test-only reader: one dict per line of <path>, in order."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


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


def test_auditrow_optional_observability_fields_are_serialized(tmp_path):
    append_row(tmp_path, _sample_row(tool_name="Write", oversight_clamp={"active": True}))
    row = json.loads((tmp_path / "audit.jsonl").read_text())
    assert row["tool_name"] == "Write"
    assert row["oversight_clamp"] == {"active": True}


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
    rows = _read_jsonl(tmp_path / "audit.jsonl")
    assert len(rows) == 2
    assert rows[0]["event"] == "live.stop"
    assert rows[1]["event"] == "pre_commit"


def test_append_row_also_chain_appends_with_matching_root(tmp_path):
    """Task 2 slice 3b (owner decision: unify): append_row's row must ALSO land in the same
    tmp_path's chain (kind='audit'), verifiable via ledger.verify_chain(root=tmp_path) -- proving
    the chain write used the CALLER's explicit root, never MAKOTO_STATE_DIR (which is unset in
    this test on purpose -- a leak to the real env would still pass a naive assertion but fail
    this one, since the chain would be empty at tmp_path)."""
    from makoto.state import ledger as _ledger
    append_row(tmp_path, _sample_row(event="live.stop"))
    assert _ledger.verify_chain(root=tmp_path) is None
    rows = _ledger.read(root=tmp_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "audit"
    assert rows[0]["event"] == "live.stop"
    assert rows[0]["prev_hash"] == ""


def test_append_row_audit_jsonl_line_carries_additive_chain_fields(tmp_path):
    """The audit.jsonl line itself gains prev_hash/row_hash as ADDITIVE fields (existing readers
    use dict.get, so this is back-compatible), and two appends chain-link correctly."""
    append_row(tmp_path, _sample_row(session_id="a"))
    append_row(tmp_path, _sample_row(session_id="b"))
    rows = _read_jsonl(tmp_path / "audit.jsonl")
    assert len(rows) == 2
    assert rows[0]["prev_hash"] == ""
    assert rows[1]["prev_hash"] == rows[0]["row_hash"]


def test_append_row_chain_fault_never_blocks_audit_jsonl_write(tmp_path, monkeypatch):
    """A chain-append fault must never lose the older, more foundational fires log -- audit.jsonl
    still gets its row even if the chain write raises."""
    import makoto.state.ledger as _ledger
    def _boom(*a, **k):
        raise RuntimeError("chain unavailable")
    monkeypatch.setattr(_ledger, "append", _boom)
    append_row(tmp_path, _sample_row(event="live.stop"))
    rows = _read_jsonl(tmp_path / "audit.jsonl")
    assert len(rows) == 1
    assert rows[0]["event"] == "live.stop"
    assert "prev_hash" not in rows[0] and "row_hash" not in rows[0]


def test_append_error_writes_to_dispatch_errors_jsonl(tmp_path):
    """append_error writes one JSON line to <state_root>/dispatch_errors.jsonl."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        append_error(tmp_path, event_id=42, pattern_id="content.phantom_citation", exc=exc)
    log = tmp_path / "dispatch_errors.jsonl"
    assert log.is_file()
    row = json.loads(log.read_text().strip())
    assert row["event_id"] == 42
    assert row["pattern_id"] == "content.phantom_citation"
    assert row["exc_type"] == "ValueError"
    assert "boom" in row["exc_message"]
    assert "ts" in row
    assert row["ts"].endswith("Z")
    from makoto.state import ledger
    chain_rows = list(ledger.read(root=tmp_path))
    assert len(chain_rows) == 1 and chain_rows[0]["kind"] == "dispatch-error"


def test_append_error_does_not_touch_audit_jsonl(tmp_path):
    """append_error MUST NOT write to audit.jsonl (separate logs)."""
    try:
        raise RuntimeError("x")
    except RuntimeError as exc:
        append_error(tmp_path, event_id=None, pattern_id=None, exc=exc)
    assert not (tmp_path / "audit.jsonl").exists()  # untouched
    assert (tmp_path / "dispatch_errors.jsonl").exists()
