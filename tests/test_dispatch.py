import io
"""end-to-end dispatcher tests for makoto/dispatch.py (SQLite(WAL) backend)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# _setup_state / _run_dispatch now live in tests/conftest.py as the `state_dir`/`run_dispatch`
# fixtures; re-imported here as plain functions (not fixture injection) because this module's
# own tests still call them directly by name. Kept importable here for backward compat / historical
# reasons — tests/test_dispatch_posture_integration.py and tests/test_check_law_confluence.py now
# import the shared plain-function twins from tests.conftest directly, not from this module.
from tests.conftest import _setup_state, _run_dispatch

# The functions that actually put an event through the dispatcher. A test that calls none of
# these has not driven anything, whatever it is named.
_DISPATCH_DRIVERS = {"_run_dispatch", "run_dispatch"}


def _dispatch_facts(state_dir) -> list:
    """read the HYBRID can't-evaluate facts (dispatch_errors.jsonl rows)."""
    f = Path(state_dir) / "dispatch_errors.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]


def test_dispatch_clean_event_exits_0_empty_stdout(tmp_path):
    """benign PreToolUse event -> no decision JSON, exit 0, and (HYBRID FP-clean) NO dispatch.* fact:
    a well-formed object envelope must never trip a can't-evaluate row."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s1",
        "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out == ""
    assert _dispatch_facts(state_dir) == [], "happy path must write zero dispatch can't-evaluate facts"


def test_dispatch_loose_comparator_emits_block_json(tmp_path):
    """PreToolUse writing a verifier with .startswith( -> block JSON on stdout.

    SPEC-5 Task 8: a PreToolUse block now renders through wire.py's real Pre shape
    (hookSpecificOutput.permissionDecision == "deny"), not the old ad-hoc top-level
    "decision" key -- see makoto/verdict.py's _pre_permission.
    """
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s1",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "constitution/integrity/checks/myverifier.py",
            "content": 'def check(x):\n    return x.startswith("ok")\n',
        },
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "expected block JSON on stdout"
    decision = json.loads(out)
    assert decision["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert "content.verifier_predicate_weakened" in reason or "loose" in reason.lower() or "startswith" in reason


def test_dispatch_unparseable_stdin_loud_allows_with_fact(tmp_path):
    """HYBRID: unparseable stdin = a transient/truncated pipe (a real envelope is always valid JSON)
    -> loud-ALLOW (exit 0) AND an on-the-record fact. Never a silent fail-open.

    The stdout assertion INVERTED on purpose. It used to require an empty wire, which made "never a
    silent fail-open" true only of the audit file -- and hook stderr on exit 0 reaches the debug log
    alone, so from the user's seat, the model's seat, and the transcript, a skipped check was
    indistinguishable from a clean pass. `systemMessage` is the universal output field that is
    actually surfaced. The fail DIRECTION is unchanged: still allow, still exit 0."""
    state_dir = _setup_state(tmp_path)
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto.dispatch"],
        input=b"not json{{{",
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent / "plugin"),
    )
    assert proc.returncode == 0
    body = json.loads(proc.stdout.decode())
    assert "ALLOWED WITHOUT BEING CHECKED" in body["systemMessage"]
    assert "permissionDecision" not in proc.stdout.decode(), "a notice must never become a decision"
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.unparseable_payload" for f in facts), facts


def _chain_path(state_dir) -> Path:
    return Path(state_dir) / "chain.jsonl"


def test_dispatch_absent_chain_self_verify_silent_no_fact(tmp_path):
    """Task 2 slice 3 (advisory-first, block-after-soak): the chain self-verify must stay silent
    when the chain is absent (verify_chain's own vacuous-clean contract) -- an ordinary session
    with no ledger activity yet must never trip a can't-evaluate fact."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    facts = _dispatch_facts(state_dir)
    assert not any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts


def test_dispatch_clean_appended_chain_self_verify_silent_no_fact(tmp_path, monkeypatch):
    """A real, untampered chain (rows actually appended) must also stay silent -- the self-verify
    is a tamper detector, not a mere-presence trip."""
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    from makoto.state import ledger as _ledger
    _ledger.append({"kind": "verdict", "key": "a"})
    _ledger.append({"kind": "verdict", "key": "b"})
    payload = {
        "hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    facts = _dispatch_facts(state_dir)
    assert not any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts


def test_dispatch_tampered_chain_self_verify_advisory_fact_never_blocks(tmp_path, monkeypatch):
    """PLANT the fault (hand-edit a chained row's field, leaving its row_hash stale) and SEE it
    fire as an advisory dispatch.chain_tamper fact -- but the session must NOT be blocked (owner
    decision: advisory-first, block-after-soak). Exit code and stdout must be identical to the
    clean-chain case; only the audit trail differs."""
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    from makoto.state import ledger as _ledger
    _ledger.append({"kind": "verdict", "key": "a"})
    _ledger.append({"kind": "verdict", "key": "b"})
    chain_file = _chain_path(state_dir)
    lines = chain_file.read_text().splitlines()
    row0 = json.loads(lines[0])
    row0["key"] = "TAMPERED"
    lines[0] = json.dumps(row0, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    chain_file.write_text("\n".join(lines) + "\n")

    payload = {
        "hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out == ""
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts


def test_dispatch_non_object_payload_blocks_exit_2_with_fact(tmp_path):
    """HYBRID: valid JSON that is NOT an object is tamper-shaped — a truncated pipe yields INVALID
    json, and Claude Code's envelope is always an object, so a parseable non-object is anomalous ->
    fail CLOSED (exit 2 + stderr reason + fact). Tested for a list, a string, and `null`."""
    state_dir = _setup_state(tmp_path)
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    for raw in (b'["not","an","object"]', b'"a bare string"', b'null'):
        proc = subprocess.run(
            [sys.executable, "-m", "makoto.dispatch"],
            input=raw, capture_output=True, env=env,
            cwd=str(Path(__file__).parent.parent / "plugin"),
        )
        assert proc.returncode == 2, (raw, proc.returncode, proc.stderr)
        assert b"object" in proc.stderr.lower(), (raw, proc.stderr)
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.non_object_payload" for f in facts), facts


def test_dispatch_db_init_failure_loud_allows_with_fact(tmp_path, monkeypatch):
    """HYBRID infra: lazy DB init failure -> loud-ALLOW (exit 0) + fact (never crash, never silent)."""
    import io
    from makoto import dispatch
    state_dir = tmp_path / "makoto_state"
    state_dir.mkdir(parents=True)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    monkeypatch.setattr(dispatch, "_ensure_db_initialized", lambda *a, **k: False)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/tmp", "tool_input": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert dispatch.main() == 0
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.db_init_failed" for f in facts), facts


def test_dispatch_db_lock_loud_allows_with_fact(tmp_path, monkeypatch):
    """HYBRID infra: write-lock not acquired -> loud-ALLOW (exit 0) + fact."""
    import io
    from makoto import dispatch
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    monkeypatch.setattr(dispatch, "_connect_with_retry", lambda *a, **k: None)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/tmp", "tool_input": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert dispatch.main() == 0
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.db_locked" for f in facts), facts


def test_dispatch_body_exception_loud_allows_with_fact(tmp_path, monkeypatch):
    """HYBRID infra: an unexpected body fault -> loud-ALLOW (exit 0, never crash to non-zero) + fact
    (Exception, not BaseException, so Ctrl-C still propagates)."""
    import io
    from makoto import dispatch
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    def boom(*a, **k):
        raise RuntimeError("ingest blew up")
    monkeypatch.setattr(dispatch, "_ingest_event", boom)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/tmp", "tool_input": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert dispatch.main() == 0
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.exception" for f in facts), facts


def test_dispatch_lazy_init_creates_db_when_absent(tmp_path):
    """if makoto.record.db is absent, dispatch.main() creates it on first call."""
    state_dir = tmp_path / "makoto_state"
    # DO NOT call init_db here — the dispatcher must create it lazily.
    state_dir.mkdir(parents=True)
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "lazy_init_test",
        "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/x.txt", "content": "hello"},
    }
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto.dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent / "plugin"),
    )
    assert proc.returncode == 0
    db_file = state_dir / "makoto.record.db"
    assert db_file.is_file(), "lazy init should have created makoto.record.db"


def test_connect_with_retry_fails_open_on_lock(monkeypatch):
    """A write lock held past the busy_timeout budget must fail OPEN: _connect_with_retry
    returns None so the caller skips evaluation and the agent's tool call proceeds.

    SQLite(WAL) makes lock contention rare (concurrent readers + busy_timeout absorb
    most of it), but the fail-open path is safety-critical — a hung lock must never
    crash or block the hook. Tested at the unit level so it is fast and deterministic
    rather than racing two processes for a lock.
    """
    import sqlite3
    from makoto import dispatch
    calls = {"n": 0}

    def _locked(*a, **kw):
        calls["n"] += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", _locked)
    assert dispatch._connect_with_retry(Path("/tmp/whatever.db")) is None
    assert calls["n"] == dispatch._LOCK_RETRY_ATTEMPTS  # retried the full budget, then gave up


def test_connect_with_retry_reraises_non_lock_errors(monkeypatch):
    """A non-lock OperationalError is a real bug, not contention — it must propagate,
    never be silently swallowed as fail-open (that would mask corruption)."""
    import sqlite3
    from makoto import dispatch
    def _boom(*a, **kw):
        raise sqlite3.OperationalError("no such table: events")

    monkeypatch.setattr(sqlite3, "connect", _boom)
    with pytest.raises(sqlite3.OperationalError):
        dispatch._connect_with_retry(Path("/tmp/whatever.db"))


def test_dispatch_skips_audit_row_when_no_findings(tmp_path):
    """only-fires audit policy: empty-findings hook fires do not append a row.

    Pre-1.0.2: every hook fire wrote a row, even when nothing matched. Real-world
    logs were 99%+ noise (~710/712 rows empty). The audit log's purpose is forensic
    review of what Makoto *detected* — silent hook fires carry no signal.
    """
    state_dir = _setup_state(tmp_path)
    audit_path = state_dir / "audit.jsonl"
    pre_size = audit_path.stat().st_size if audit_path.exists() else 0
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "noise",
        "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello world"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out == ""
    post_size = audit_path.stat().st_size if audit_path.exists() else 0
    assert post_size == pre_size, (
        f"empty-findings hook must not write an audit row; size grew {pre_size}->{post_size}"
    )


def test_dispatch_still_writes_audit_row_when_finding_fires(tmp_path):
    """only-fires policy must NOT silence real fires — content.verifier_predicate_weakened still records its row."""
    state_dir = _setup_state(tmp_path)
    audit_path = state_dir / "audit.jsonl"
    pre_size = audit_path.stat().st_size if audit_path.exists() else 0
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "real_fire",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "/tmp/constitution/integrity/checks/test_block.py",
            "content": 'def check(s): return s.startswith("ok")\n',
        },
    }
    rc, out = _run_dispatch(state_dir, payload)
    # SPEC-5 Task 8: a PreToolUse block renders wire.py's real Pre shape (deny), not a literal
    # "block" substring -- see test_dispatch_loose_comparator_emits_block_json for the full shape.
    assert '"deny"' in out, f"content.verifier_predicate_weakened should still emit a deny decision; got {out!r}"
    assert audit_path.exists()
    post_size = audit_path.stat().st_size
    assert post_size > pre_size, "fire-row must be recorded"


def test_dispatch_env_disable_silences_specific_pattern(tmp_path):
    """MAKOTO_DISABLE_PATTERNS=content.verifier_predicate_weakened makes content.verifier_predicate_weakened a no-op for this dispatcher call.

    The same payload that fires content.verifier_predicate_weakened under normal config must produce no block JSON
    and no audit row when the env var lists 1.1. Other patterns continue normally.
    """
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "disable_test",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "/tmp/constitution/integrity/checks/test_block.py",
            "content": 'def check(s): return s.startswith("ok")\n',
        },
    }
    rc, out = _run_dispatch(state_dir, payload, extra_env={"MAKOTO_DISABLE_PATTERNS": "content.verifier_predicate_weakened"})
    assert out == "", f"disabled pattern must not emit block JSON; got {out!r}"
    audit_path = state_dir / "audit.jsonl"
    if audit_path.exists():
        rows = [json.loads(l) for l in audit_path.read_text().splitlines() if l.strip()]
        assert not any("content.verifier_predicate_weakened" in r.get("pattern_fires", []) for r in rows), \
            "disabled pattern must not record a fire row"


def test_dispatch_audit_row_records_tool_name(tmp_path):
    """1.0.2: AuditRow.tool_name is populated from payload so fires are mineable by tool."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "tool_name_test",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "/tmp/constitution/integrity/checks/test_block.py",
            "content": 'def check(s): return s.startswith("ok")\n',
        },
    }
    rc, _ = _run_dispatch(state_dir, payload)
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0].get("tool_name") == "Write", (
        f"expected tool_name='Write' on fire row; got {rows[0].get('tool_name')!r}"
    )
    assert rows[0]["pattern_fires"] == ["content.verifier_predicate_weakened"]


def test_dispatch_posttooluse_write_records_ledger_touch(tmp_path):
    """PostToolUse Write -> a `touched` ledger row (the update recorder, wired live)."""
    import sqlite3
    from makoto.state import ledger
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "ledger_write",
        "cwd": "/tmp",
        "tool_input": {"file_path": "src/auth.py", "content": "x"},
        "tool_response": {"filePath": "src/auth.py"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out == "", "PostToolUse must never emit a decision"
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    try:
        row = ledger.read_key(conn, "src/auth.py")
    finally:
        conn.close()
    assert row is not None and row["kind"] == "touched", f"expected touched row; got {row!r}"


def test_dispatch_failed_write_stays_in_history_without_recording_a_touch(tmp_path):
    """PostToolUseFailure is failure evidence, not a successful filesystem update.

    The terminal must remain in ``events`` for history decoders, but must not create the
    success-shaped ``touched`` row that completion/dropped/advance gates treat as discharge.
    """
    import sqlite3
    from makoto.state import ledger

    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Write",
        "session_id": "failed_ledger_write",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "src/never-created.py", "content": "x"},
        "error": "permission denied",
        "is_interrupt": False,
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert rc == 0 and out == ""

    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    try:
        assert ledger.read_key(conn, "src/never-created.py") is None
        event_type, raw = conn.execute(
            "SELECT event_type, payload FROM events WHERE session_id = ?",
            ["failed_ledger_write"],
        ).fetchone()
    finally:
        conn.close()
    assert event_type == "PostToolUseFailure"
    assert json.loads(raw)["error"] == "permission denied"


def test_dispatch_posttooluse_bash_records_ledger_value(tmp_path):
    """PostToolUse Bash -> a `value` ledger row keyed by the path token in the command."""
    import sqlite3
    from makoto.state import ledger
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": "ledger_bash",
        "cwd": "/tmp",
        "tool_input": {"command": "wc -l tests/auth_test.py"},   # non-runner -> a generic value row
        "tool_response": {"stdout": "120 tests/auth_test.py", "stderr": "", "exitCode": 0},
    }
    rc, _ = _run_dispatch(state_dir, payload)
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    try:
        row = ledger.read_key(conn, "tests/auth_test.py")
    finally:
        conn.close()
    assert row is not None and row["kind"] == "value", f"expected value row; got {row!r}"
    assert "120 tests/auth_test.py" in (row["value"] or "")


def test_dispatch_failed_terminal_does_not_clobber_prior_failing_testrun(tmp_path):
    """A failed hook terminal has no runner output and cannot supersede a real red result."""
    import sqlite3
    from makoto.kit import is_failing_testrun
    from makoto.state import ledger

    state_dir = _setup_state(tmp_path)
    sid = "failed_testrun_terminal"
    command = "python -m pytest tests/ -q"
    red = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": sid,
        "cwd": str(tmp_path),
        "tool_input": {"command": command},
        "tool_response": {
            "stdout": "=== 2 failed, 9 passed in 3.0s ===",
            "stderr": "",
            "exitCode": 1,
        },
    }
    failed_terminal = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "session_id": sid,
        "cwd": str(tmp_path),
        "tool_input": {"command": command},
        "error": "Connection error",
        "is_interrupt": False,
    }
    assert _run_dispatch(state_dir, red) == (0, "")
    assert _run_dispatch(state_dir, failed_terminal) == (0, "")

    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    try:
        latest = ledger.latest_testrun(conn, sid)
        source_event_id = conn.execute(
            "SELECT source_event_id FROM ledger WHERE session_id = ? AND kind = 'testrun'",
            [sid],
        ).fetchone()[0]
        event_types = [row[0] for row in conn.execute(
            "SELECT event_type FROM events WHERE session_id = ? ORDER BY id", [sid]
        )]
    finally:
        conn.close()
    assert is_failing_testrun(latest) is True
    assert source_event_id == 1
    assert event_types == ["PostToolUse", "PostToolUseFailure"]


def test_dispatch_completion_gate_blocks_by_default(tmp_path):
    """2026-06-01 flip: an unbacked PRODUCTION claim (a produce verb governs an absent path)
    BLOCKS live by default — no env var needed. This is the validated completion gate."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "gate_default",
        "cwd": str(tmp_path),  # the cited file definitely does not exist under here
        "last_assistant_message": "Done - added rate limiting to src/nonexistent_zzz.py",
    }
    rc, out = _run_dispatch(state_dir, payload)   # no env -> completion gate blocks live
    assert out, "completion gate must block by default after the flip"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "src/nonexistent_zzz.py" in decision["reason"]


def test_dispatch_green_claim_gate_blocks_after_recorded_red_run(tmp_path):
    """end-to-end connectivity: a failing pytest recorded at PostToolUse, then a WHOLE-SUITE green
    claim at Stop -> gate.green_claim BLOCKS live (corpus-FP=0, measured POWERED)."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "gc",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "=== 2 failed, 9 passed in 3.0s ===", "stderr": "",
                              "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)              # records the red run -> kind='testrun'
    stop = {"hook_event_name": "Stop", "session_id": "gc", "cwd": str(tmp_path),
            "last_assistant_message": "Done — all tests pass now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "green_claim gate must block on a green claim over a recorded red run"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "test" in decision["reason"].lower()


def test_dispatch_run_promised_gate_blocks_after_an_unkept_promise(tmp_path):
    """A turn that ends promising a run, then a turn that ends with no Bash call recorded between:
    the second Stop is blocked by gate.run_promised (f2 of the f1-f4 probe)."""
    state_dir = _setup_state(tmp_path)
    first = {"hook_event_name": "Stop", "session_id": "rp", "cwd": str(tmp_path),
             "last_assistant_message": "I'll run all 602 checks now."}
    _run_dispatch(state_dir, first)
    second = dict(first, last_assistant_message="Done.")
    rc, out = _run_dispatch(state_dir, second)
    assert out, "gate.run_promised must block the Stop after an unkept run promise"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.run_promised" in decision["reason"]


def test_dispatch_green_claim_silent_after_green_run(tmp_path):
    """control: the SAME green claim but the recorded run PASSED -> no contradiction -> no block."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "gc2",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "=== 11 passed in 3.0s ===", "stderr": "", "exitCode": 0}}
    _run_dispatch(state_dir, post)
    stop = {"hook_event_name": "Stop", "session_id": "gc2", "cwd": str(tmp_path),
            "last_assistant_message": "Done — all tests pass now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert "gate.green_claim" not in out, "run was green -> green_claim gate must stay silent"


def test_dispatch_completion_gate_shadow_when_disabled(tmp_path):
    """MAKOTO_DISABLE_GATES=1 returns the completion gate to shadow: still audited, no block
    (the escape valve if a real-session false-block ever surfaces)."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "gate_shadow",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done - added rate limiting to src/nonexistent_zzz.py",
    }
    rc, out = _run_dispatch(state_dir, payload, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    assert out == "", "disabled completion gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.completion" in r.get("pattern_fires", []) for r in rows), \
        "the shadow gate fire must still be audited so its FP rate can be mined"


def test_dispatch_completion_gate_silent_on_mere_path_mention(tmp_path):
    """FP guard, end to end: a path merely REFERENCED at Stop (no production verb governing it)
    must NOT block even with the gate live — the production-claim-binding fix."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "gate_ref",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done reviewing. See src/nonexistent_zzz.py for the details.",
    }
    rc, out = _run_dispatch(state_dir, payload)   # gate live, but no production claim
    assert "gate.completion" not in out, "a referenced (not produced) path must not false-block"


def test_dispatch_dropped_gate_blocks_by_default(tmp_path):
    """Behavioral blocking pin for gate.dropped THROUGH the real dispatch — the falsifiability gap
    its 3 sibling gates each closed but it landed without. A forward promise carrying identifying
    info (a named symbol), left undischarged at turn-end (file absent, no Write recorded), BLOCKS
    live by default. Breaking the dispatcher's Stop-gate wiring reddens THIS (not just the structural
    set-equality test), proving gate.dropped actually stops the agent, not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "drop_default",
        "cwd": str(tmp_path),  # src/gates_zzz.py does not exist here -> undischarged
        "last_assistant_message": "I'll add def validate_seal_zzz to src/gates_zzz.py next.",
    }
    rc, out = _run_dispatch(state_dir, payload)   # no env -> dropped gate blocks live
    assert out, "dropped gate must block by default on an undischarged forward promise"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "validate_seal_zzz" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.dropped" in r.get("pattern_fires", []) for r in rows), \
        "the dropped fire must still be audited"


def test_dispatch_dropped_gate_silent_when_discharged(tmp_path):
    """Control proving the gate DISCRIMINATES end-to-end (not fire-on-everything): the SAME forward
    promise, but the named symbol IS present in the cited file on disk -> discharged -> no block."""
    state_dir = _setup_state(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "gates_zzz.py").write_text("def validate_seal_zzz():\n    return True\n")
    payload = {
        "hook_event_name": "Stop",
        "session_id": "drop_met",
        "cwd": str(tmp_path),
        "last_assistant_message": "I'll add def validate_seal_zzz to src/gates_zzz.py next.",
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert "gate.dropped" not in out, "a discharged promise (symbol present on disk) must not block"


def test_dispatch_dropped_gate_shadow_when_disabled(tmp_path):
    """MAKOTO_DISABLE_GATES=1 returns the dropped gate to shadow: still audited, no block — the
    same single escape valve the other three blocking gates share."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "drop_off",
        "cwd": str(tmp_path),
        "last_assistant_message": "I'll add def validate_seal_zzz to src/gates_zzz.py next.",
    }
    rc, out = _run_dispatch(state_dir, payload, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    assert out == "", "disabled dropped gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.dropped" in r.get("pattern_fires", []) for r in rows), \
        "the shadow dropped fire must still be audited so its FP rate can be mined"


def test_dispatch_liveness_gate_blocks_on_illusory_code(tmp_path):
    """Behavioral blocking pin for the liveness gate THROUGH the real dispatch. A .py file
    touched this turn (recorded via a PostToolUse Write -> ledger touched-key) and present on disk
    with a dead pure statement (a value computed and never reaching I/O) BLOCKS at Stop by default.
    Breaking the dispatcher's Stop-gate wiring reddens THIS, proving the gate actually stops the
    agent end-to-end, not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    (tmp_path / "dead.py").write_text("def fn():\n d = 1 + 1\n return 0\n")   # on disk for fs_read
    write_ev = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "live_block",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "dead.py", "content": "def fn():\n d = 1 + 1\n return 0\n"},
        "tool_response": {"filePath": "dead.py"},
    }
    rc, out = _run_dispatch(state_dir, write_ev)            # records the touched ledger key
    assert rc == 0 and out == ""
    stop = {
        "hook_event_name": "Stop",
        "session_id": "live_block",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done — added the helper.",
    }
    rc, out = _run_dispatch(state_dir, stop)                # no env -> liveness gate blocks live
    assert out, "liveness gate must block by default on a touched file with illusory code"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "illusory" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.liveness" in r.get("pattern_fires", []) for r in rows), \
        "the liveness fire must still be audited"


def test_dispatch_liveness_gate_silent_when_code_is_material(tmp_path):
    """Control proving the gate DISCRIMINATES end-to-end: the SAME touched file, but its
    computed value reaches the return (material, not illusory) -> no block."""
    state_dir = _setup_state(tmp_path)
    (tmp_path / "live.py").write_text("def fn():\n d = 1 + 1\n return d\n")
    write_ev = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "live_ok",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "live.py", "content": "def fn():\n d = 1 + 1\n return d\n"},
        "tool_response": {"filePath": "live.py"},
    }
    rc, out = _run_dispatch(state_dir, write_ev)
    assert rc == 0 and out == ""
    stop = {
        "hook_event_name": "Stop",
        "session_id": "live_ok",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done — added the helper.",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert "gate.liveness" not in out, "a material statement (its value reaches the return) must not block"


def test_dispatch_liveness_gate_shadow_when_disabled(tmp_path):
    """MAKOTO_DISABLE_GATES=1 returns the liveness gate to shadow: still audited, no block —
    the same single escape valve the Stop gates share."""
    state_dir = _setup_state(tmp_path)
    (tmp_path / "dead.py").write_text("def fn():\n d = 1 + 1\n return 0\n")
    write_ev = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "live_off",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "dead.py", "content": "def fn():\n d = 1 + 1\n return 0\n"},
        "tool_response": {"filePath": "dead.py"},
    }
    _run_dispatch(state_dir, write_ev, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    stop = {
        "hook_event_name": "Stop",
        "session_id": "live_off",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done — added the helper.",
    }
    rc, out = _run_dispatch(state_dir, stop, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    assert out == "", "disabled liveness gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.liveness" in r.get("pattern_fires", []) for r in rows), \
        "the shadow liveness fire must still be audited so its FP rate can be mined"


def test_dispatch_hollow_test_gate_blocks_on_hollow_test(tmp_path):
    """Behavioral blocking pin for gate.hollow_test THROUGH the real dispatch. A test file touched
    this turn (recorded via a PostToolUse Write -> ledger touched-key) and present on disk with a
    HOLLOWED test (no assertion of any kind) BLOCKS at Stop by default. Breaking the
    dispatcher's Stop-gate wiring reddens THIS, proving the gate actually stops the agent end-to-end,
    not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    src = "def test_a():\n    x = compute()\n"
    (tmp_path / "test_hollow.py").write_text(src)          # on disk for fs_read
    write_ev = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "hollow_block",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "test_hollow.py", "content": src},
        "tool_response": {"filePath": "test_hollow.py"},
    }
    rc, out = _run_dispatch(state_dir, write_ev)            # records the touched ledger key
    assert rc == 0 and out == ""
    stop = {
        "hook_event_name": "Stop",
        "session_id": "hollow_block",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done — added the test.",
    }
    rc, out = _run_dispatch(state_dir, stop)                # no env -> hollow_test gate blocks live
    assert out, "hollow_test gate must block by default on a touched test file with no assertion"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "hollow" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.hollow_test" in r.get("pattern_fires", []) for r in rows), \
        "the hollow_test fire must still be audited"


def test_dispatch_hollow_test_gate_silent_when_test_has_a_real_assertion(tmp_path):
    """Control proving the gate DISCRIMINATES end-to-end: the SAME touched test file, but with a
    real assertion in its body -> no block."""
    state_dir = _setup_state(tmp_path)
    src = "def test_a():\n    assert compute() == 1\n"
    (tmp_path / "test_ok.py").write_text(src)
    write_ev = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "hollow_ok",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "test_ok.py", "content": src},
        "tool_response": {"filePath": "test_ok.py"},
    }
    rc, out = _run_dispatch(state_dir, write_ev)
    assert rc == 0 and out == ""
    stop = {
        "hook_event_name": "Stop",
        "session_id": "hollow_ok",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done — added the test.",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert "gate.hollow_test" not in out, "a test with a real assertion must not block"


def test_dispatch_canon_gate_blocks_by_default(tmp_path):
    """Behavioral blocking pin for gate.canon THROUGH the real dispatch. A Bash call recorded at
    PostToolUse with tool_response={"interrupted": true} and nothing after it -> the turn's LAST
    call is in a direct error state -> canon.timeout fires and BLOCKS at Stop by default. Breaking
    the dispatcher's Stop-gate wiring reddens THIS, proving the gate actually stops the agent
    end-to-end, not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "canon_block",
            "cwd": str(tmp_path),
            "tool_input": {"command": "some-long-running-thing"},
            "tool_response": {"interrupted": True}}
    rc, out = _run_dispatch(state_dir, post)              # records the call -> history
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": "canon_block", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)              # no env -> canon gate blocks live
    assert out, "canon gate must block by default on an unresolved interrupted call at turn-end"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "canon.timeout" in decision["reason"]           # sub-primitive named in the message


def test_dispatch_canon_fingerprints_gate_blocks(tmp_path):
    """Behavioral blocking pin for gate.canon_fingerprints (SPEC-5 Task 9) THROUGH the real
    dispatch. A bare destructive Bash call with no source edit and no failing test run fires
    nosrc_destruct (NOT_edit_test_after_red ∧ NOT_source_edited ∧ destructive_command, a
    robust-core, blocking-capable fingerprint) and BLOCKS at Stop by default."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "canon_fp_block",
            "cwd": str(tmp_path), "tool_input": {"command": "rm -rf /tmp/scratch"},
            "tool_response": {"stdout": "", "stderr": "", "exitCode": 0}}
    rc, out = _run_dispatch(state_dir, post)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": "canon_fp_block", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "gate.canon_fingerprints must block by default on a robust-core fingerprint fire"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "canon.nosrc_destruct" in decision["reason"]


def test_dispatch_canon_gate_silent_when_resolved_before_turn_end(tmp_path):
    """Control proving the gate DISCRIMINATES end-to-end: the SAME interrupted call, but a LATER
    successful Bash call closes the turn -> the error was resolved -> no block."""
    state_dir = _setup_state(tmp_path)
    sid = "canon_resolved"
    failed = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
              "cwd": str(tmp_path),
              "tool_input": {"command": "flaky-thing"},
              "tool_response": {"interrupted": True}}
    ok = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
          "cwd": str(tmp_path),
          "tool_input": {"command": "flaky-thing --retry"},
          "tool_response": {"stdout": "done", "stderr": ""}}
    _run_dispatch(state_dir, failed)
    _run_dispatch(state_dir, ok)
    stop = {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out == "", "a resolved-then-fixed error must not block"


def test_dispatch_canon_gate_shadow_when_disabled(tmp_path):
    """MAKOTO_DISABLE_GATES=1 returns the canon gate to shadow: still audited, no block — the
    same single escape valve the other blocking gates share."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "canon_off",
            "cwd": str(tmp_path),
            "tool_input": {"command": "some-long-running-thing"},
            "tool_response": {"interrupted": True}}
    _run_dispatch(state_dir, post, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    stop = {"hook_event_name": "Stop", "session_id": "canon_off", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    assert out == "", "disabled canon gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.canon" in r.get("pattern_fires", []) for r in rows), \
        "the shadow canon fire must still be audited so its FP rate can be mined"


def test_dispatch_fabricated_action_gate_blocks(tmp_path):
    """Behavioral blocking pin for gate.fabricated_action THROUGH the real dispatch. A Stop message
    claims a completed tool action with a distinctive (backticked) object whose command NO recorded
    tool event this session ran -> the gate walks ctx.history (the events-table slice, empty of any
    matching command here) -> BLOCKS live by default. Breaking the history wiring
    reddens THIS, proving the fabricated-action claim actually stops the agent end-to-end."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "fab_action",
        "cwd": str(tmp_path),
        "last_assistant_message": "I ran `pytest tests/zzz_unrun.py -q` and it all passed.",
    }
    rc, out = _run_dispatch(state_dir, payload)   # no prior command recorded -> fabricated -> blocks
    assert out, "fabricated_action gate must block a tool-action claim with no recorded command"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "pytest tests/zzz_unrun.py -q" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.fabricated_action" in r.get("pattern_fires", []) for r in rows), \
        "the fabricated_action fire must be audited"


def test_dispatch_fabricated_action_silent_when_command_ran(tmp_path):
    """Control proving the gate DISCRIMINATES end-to-end on PRESENCE of tool work: the SAME action
    claim, but a tool call really happened this turn (a PreToolUse event — every tool call emits one,
    matcher '*') -> turn_tool_calls > 0 -> discharged -> no block. The discharge is presence-of-work,
    NOT command-text matching, so it is immune to paraphrase and to invisible tools."""
    state_dir = _setup_state(tmp_path)
    pre = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "fab_ok",
           "cwd": str(tmp_path),
           "tool_input": {"command": "python -m pytest tests/zzz_unrun.py -q --tb=short"}}
    _run_dispatch(state_dir, pre)                  # a tool call really happened this turn
    stop = {"hook_event_name": "Stop", "session_id": "fab_ok", "cwd": str(tmp_path),
            "last_assistant_message": "I ran `pytest tests/zzz_unrun.py -q` and it all passed."}
    rc, out = _run_dispatch(state_dir, stop)
    assert "gate.fabricated_action" not in out, \
        "a tool call this turn discharges the action claim -> must not block"


def test_dispatch_named_test_gate_blocks_after_recorded_named_red(tmp_path):
    """Behavioral blocking pin for gate.named_test THROUGH the real dispatch. A failing PER-TEST run
    (FAILED ...::test_foo) recorded at PostToolUse, then a claim that test_foo passes at Stop -> the
    gate reads the per-name verdict from ctx.history -> BLOCKS live. Breaking the
    history wiring reddens THIS, proving the named-test claim stops the agent end-to-end."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "nt",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "FAILED tests/x.py::test_foo - AssertionError\n1 failed in 0.1s",
                              "stderr": "", "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)              # records the per-test red into history
    stop = {"hook_event_name": "Stop", "session_id": "nt", "cwd": str(tmp_path),
            "last_assistant_message": "Good news — test_foo passes now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "named_test gate must block a named-test pass-claim over that test's recorded red"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "test_foo" in decision["reason"]


def test_dispatch_claimed_running_gate_blocks_after_recorded_failed_launch(tmp_path):
    """Behavioral blocking pin for gate.claimed_running THROUGH the real dispatch. A backgrounded
    launch recorded at PostToolUse as interrupted, then a Stop claim that the server is running ->
    the gate reads the most recently recorded process-lifecycle call from ctx.history -> BLOCKS live
    by default. Breaking the history wiring reddens THIS, proving the
    running claim stops the agent end-to-end, not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "run_block",
            "cwd": str(tmp_path),
            "tool_input": {"command": "npm run dev &"},
            "tool_response": {"interrupted": True}}
    rc, _ = _run_dispatch(state_dir, post)              # records the failed launch into history
    stop = {"hook_event_name": "Stop", "session_id": "run_block", "cwd": str(tmp_path),
            "last_assistant_message": "I started the server. It is now running on port 3000."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "claimed_running gate must block a running claim over a recorded failed launch"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "direct error state" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.claimed_running" in r.get("pattern_fires", []) for r in rows), \
        "the claimed_running fire must be audited"


def test_dispatch_unexamined_wall_gate_blocks_when_no_act_followed_the_operator(tmp_path):
    """Behavioral blocking pin for gate.unexamined_wall (register G5) through the real dispatcher.

    One genuine operator turn sets the window boundary; the session then records no tool call at
    all, and the agent states that a fact cannot be determined. That is a wall declared with the
    inventory unopened. The negative half is the next test."""
    state_dir = _setup_state(tmp_path)
    tp = tmp_path / "wall.jsonl"
    tp.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "carry on"},
                              "timestamp": "2026-09-08T10:00:00Z"}) + "\n", encoding="utf-8")
    stop = {"hook_event_name": "Stop", "session_id": "wall_block", "cwd": str(tmp_path),
            "transcript_path": str(tp),
            "last_assistant_message": "There is no way to tell whether the suite passes."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "unexamined_wall must block an epistemic cannot stated with an empty act window"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    rows = [json.loads(line) for line in (state_dir / "audit.jsonl").read_text().splitlines()
            if line.strip()]
    assert any("gate.unexamined_wall" in row.get("pattern_fires", []) for row in rows), \
        "the unexamined_wall fire must be audited"


def test_dispatch_unexamined_wall_is_silent_when_a_refusal_is_not_epistemic(tmp_path):
    """A refusal asserts nothing about what is knowable, so it is not G5 and must not block.
    Without this cell the gate would be a can't-word matcher rather than a wall detector."""
    state_dir = _setup_state(tmp_path)
    tp = tmp_path / "wall2.jsonl"
    tp.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "carry on"},
                              "timestamp": "2026-09-08T10:00:00Z"}) + "\n", encoding="utf-8")
    stop = {"hook_event_name": "Stop", "session_id": "wall_ok", "cwd": str(tmp_path),
            "transcript_path": str(tp),
            "last_assistant_message": "I can't help with that request."}
    rc, out = _run_dispatch(state_dir, stop)
    if out:
        assert "gate.unexamined_wall" not in out


def test_dispatch_claimed_consent_absent_gate_blocks_when_the_operator_never_spoke(tmp_path):
    """Behavioral blocking pin for gate.claimed_consent_absent through the real dispatcher.

    The transcript holds one user-ROLE entry carrying toolUseResult, which `_is_genuine_user_turn`
    refuses -- so the oracle channel is empty and the agent's citation of operator approval is
    attributed to a record that has nothing in it. The negative half is the next test: one genuine
    turn is enough to silence this, because whether the claim MATCHES that turn is a similarity
    question the check deliberately does not answer."""
    state_dir = _setup_state(tmp_path)
    tp = tmp_path / "transcript.jsonl"
    tp.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "ok"},
                              "toolUseResult": {"stdout": ""},
                              "timestamp": "2026-09-08T10:00:00Z"}) + "\n", encoding="utf-8")
    stop = {"hook_event_name": "Stop", "session_id": "consent_block", "cwd": str(tmp_path),
            "transcript_path": str(tp),
            "last_assistant_message": "You approved this, so I went ahead and merged it."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "claimed_consent_absent must block a citation of operator approval with no operator turn"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    rows = [json.loads(line) for line in (state_dir / "audit.jsonl").read_text().splitlines()
            if line.strip()]
    assert any("gate.claimed_consent_absent" in row.get("pattern_fires", []) for row in rows), \
        "the claimed_consent_absent fire must be audited"


def test_claimed_consent_absent_catches_green_light_reword(tmp_path):
    """Same consent-citation intent as 'you approved', reworded as 'gave the green light' --
    must not need the closed approved/confirmed/... verb list."""
    from makoto.checks.otherPoint import claimed_consent_absent_gate
    tp = tmp_path / "transcript.jsonl"
    tp.write_text("", encoding="utf-8")
    finding = claimed_consent_absent_gate(
        "Since you gave the green light on this, I proceeded.", transcript_path=str(tp))
    assert finding is not None
    assert finding.pattern_id == "gate.claimed_consent_absent"


def test_dispatch_claimed_consent_absent_is_silent_when_the_operator_has_spoken(tmp_path):
    """One genuine operator turn silences it. Without this the check would be a paraphrase judge,
    and paraphrase is judgement; absence of the whole channel is what it counts."""
    state_dir = _setup_state(tmp_path)
    tp = tmp_path / "transcript.jsonl"
    tp.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "go ahead"},
                              "timestamp": "2026-09-08T10:00:00Z"}) + "\n", encoding="utf-8")
    stop = {"hook_event_name": "Stop", "session_id": "consent_ok", "cwd": str(tmp_path),
            "transcript_path": str(tp),
            "last_assistant_message": "You approved this, so I went ahead and merged it."}
    rc, out = _run_dispatch(state_dir, stop)
    if out:
        assert "gate.claimed_consent_absent" not in out


def test_dispatch_claimed_shipped_gate_blocks_on_unbacked_remote_claim(tmp_path):
    """Behavioral blocking pin for gate.claimed_shipped through the real dispatcher: an immediate
    completed merge claim with no prior successful remote mutation must produce a block decision
    and an audit fire."""
    state_dir = _setup_state(tmp_path)
    stop = {"hook_event_name": "Stop", "session_id": "ship_block", "cwd": str(tmp_path),
            "last_assistant_message": "I merged the PR."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "claimed_shipped gate must block an unbacked completed remote-action claim"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "remote change was shipped" in decision["reason"]
    rows = [json.loads(line) for line in (state_dir / "audit.jsonl").read_text().splitlines()
            if line.strip()]
    assert any("gate.claimed_shipped" in row.get("pattern_fires", []) for row in rows), \
        "the claimed_shipped fire must be audited"


def test_dispatch_named_test_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop falsifier: the same fabricated named-test pass-claim that blocks through Stop
    (test_dispatch_named_test_gate_blocks_after_recorded_named_red above) must block IDENTICALLY
    when it arrives as a SubagentStop event — a sub-agent's own completion claim is checked by the
    same gates a main-thread Stop claim is checked by. Breaking the `hook_event in ("Stop",
    "SubagentStop")` branch in dispatch.main() reddens this while leaving the Stop-path sibling
    test green, proving the SubagentStop route specifically."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "nt_sub",
            "agent_id": "named-test-agent",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "FAILED tests/x.py::test_foo - AssertionError\n1 failed in 0.1s",
                              "stderr": "", "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)              # records the per-test red into history
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "nt_sub", "cwd": str(tmp_path),
                     "agent_id": "named-test-agent",
                      "last_assistant_message": "Good news — test_foo passes now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert out, "named_test gate must block a named-test pass-claim through SubagentStop too"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "test_foo" in decision["reason"]


def test_dispatch_subagent_stop_audit_row_labeled_live_subagent_stop(tmp_path):
    """_EVENT_MAP must label a firing SubagentStop event's audit row `live.subagent_stop` (mirrors
    how a firing Stop event is labeled `live.stop`), so SubagentStop fires are distinguishable from
    Stop fires in the audit trail rather than collapsing to the raw hook name or an empty label."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "SubagentStop",
        "session_id": "subagent_label",
        "cwd": str(tmp_path),
        "last_assistant_message": "I ran `pytest tests/zzz_unrun.py -q` and it all passed.",
    }
    rc, out = _run_dispatch(state_dir, payload)   # no prior command recorded -> fabricated -> blocks
    assert out, "fabricated_action gate must fire through SubagentStop to produce an audit row"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["event"] == "live.subagent_stop", (
        f"expected event='live.subagent_stop'; got {rows[0]['event']!r}"
    )
    assert rows[0]["hook_kind"] == "SubagentStop"


# ---------------------------------------------------------------------------
# B3 (Makoto intent-gap audit, 2026-07-06): commit 49a4ec3 wired SubagentStop through the same
# `hook_event in ("Stop", "SubagentStop")` branch as Stop, but only exercised it against 2 of the
# 11 discovered Stop gates (named_test, fabricated_action above). The other 9 were untested-but-
# plausibly-covered by the shared code path. Each test below mirrors an EXISTING Stop-event
# behavioral pin (named in its docstring) with the final firing event changed from "Stop" to
# "SubagentStop" — same scenario, same assertions — so a future regression that special-cases Stop
# in the routing (rather than treating SubagentStop identically) reddens here per-gate, not just
# for the 2 gates already covered.
# ---------------------------------------------------------------------------


def test_dispatch_completion_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_completion_gate_blocks_by_default."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "SubagentStop",
        "session_id": "gate_default_sub",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done - added rate limiting to src/nonexistent_zzz.py",
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "completion gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "src/nonexistent_zzz.py" in decision["reason"]


def test_dispatch_green_claim_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_green_claim_gate_blocks_after_recorded_red_run."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "gc_sub",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "=== 2 failed, 9 passed in 3.0s ===", "stderr": "",
                              "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "gc_sub", "cwd": str(tmp_path),
                      "last_assistant_message": "Done — all tests pass now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert out, "green_claim gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "test" in decision["reason"].lower()


def test_dispatch_dropped_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_dropped_gate_blocks_by_default."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "SubagentStop",
        "session_id": "drop_default_sub",
        "cwd": str(tmp_path),
        "last_assistant_message": "I'll add def validate_seal_zzz to src/gates_zzz.py next.",
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "dropped gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "validate_seal_zzz" in decision["reason"]


def test_dispatch_liveness_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_liveness_gate_blocks_on_illusory_code."""
    state_dir = _setup_state(tmp_path)
    (tmp_path / "dead.py").write_text("def fn():\n d = 1 + 1\n return 0\n")
    write_ev = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "live_block_sub",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "dead.py", "content": "def fn():\n d = 1 + 1\n return 0\n"},
        "tool_response": {"filePath": "dead.py"},
    }
    rc, out = _run_dispatch(state_dir, write_ev)
    assert rc == 0 and out == ""
    subagent_stop = {
        "hook_event_name": "SubagentStop",
        "session_id": "live_block_sub",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done — added the helper.",
    }
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert out, "liveness gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "illusory" in decision["reason"]


def test_dispatch_hollow_test_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_hollow_test_gate_blocks_on_hollow_test."""
    state_dir = _setup_state(tmp_path)
    src = "def test_a():\n    x = compute()\n"
    (tmp_path / "test_hollow.py").write_text(src)
    write_ev = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "session_id": "hollow_block_sub",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": "test_hollow.py", "content": src},
        "tool_response": {"filePath": "test_hollow.py"},
    }
    rc, out = _run_dispatch(state_dir, write_ev)
    assert rc == 0 and out == ""
    subagent_stop = {
        "hook_event_name": "SubagentStop",
        "session_id": "hollow_block_sub",
        "cwd": str(tmp_path),
        "last_assistant_message": "Done — added the test.",
    }
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert out, "hollow_test gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "hollow" in decision["reason"]


def test_dispatch_canon_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_canon_gate_blocks_by_default."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "canon_block_sub",
            "agent_id": "canon-agent",
            "cwd": str(tmp_path),
            "tool_input": {"command": "some-long-running-thing"},
            "tool_response": {"interrupted": True}}
    rc, out = _run_dispatch(state_dir, post)
    assert rc == 0 and out == ""
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "canon_block_sub",
                     "agent_id": "canon-agent",
                      "cwd": str(tmp_path), "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert out, "canon gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "canon.timeout" in decision["reason"]


def test_dispatch_stale_pass_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_stale_pass_gate_blocks_on_live_lastfailed."""
    state_dir = _setup_state(tmp_path)
    cache = tmp_path / ".pytest_cache" / "v" / "cache"
    cache.mkdir(parents=True)
    (cache / "lastfailed").write_text(json.dumps({"tests/t.py::test_red": True}))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("def test_red():\n    assert False\n")
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "sp_sub", "cwd": str(tmp_path),
                      "last_assistant_message": "Done — all tests pass."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert out, "stale_pass gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "tests/t.py::test_red" in decision["reason"]


def test_dispatch_self_wired_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_self_wired_gate_blocks_when_it_fires: the
    advisory-only exception (DESIGN DECISION, 2026-07-05) must never block through SubagentStop
    either — fires (audited) but never turns into a block decision, matching the Stop-event pin."""
    state_dir = _setup_state(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto.dispatch"}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto.dispatch"}]}],
        # Stop entry deliberately absent -> a partial strip -> gate.self_wired fires, advisory only.
    }}))
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "sw_sub", "cwd": str(tmp_path),
                      "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert out, "gate.self_wired must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.self_wired" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.self_wired" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited through SubagentStop too"


def test_dispatch_stale_pass_gate_blocks_on_live_lastfailed(tmp_path):
    """Behavioral blocking pin for gate.stale_pass THROUGH the real dispatch. pytest's own
    lastfailed under the Stop payload's cwd names a failing node whose test STILL EXISTS, and the
    final message makes a clean whole-suite pass-claim -> the gate reads the on-disk record via
    ctx.cwd -> BLOCKS live. Breaking the cwd wiring reddens THIS."""
    state_dir = _setup_state(tmp_path)
    cache = tmp_path / ".pytest_cache" / "v" / "cache"
    cache.mkdir(parents=True)
    (cache / "lastfailed").write_text(json.dumps({"tests/t.py::test_red": True}))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("def test_red():\n    assert False\n")
    stop = {"hook_event_name": "Stop", "session_id": "sp", "cwd": str(tmp_path),
            "last_assistant_message": "Done — all tests pass."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "stale_pass gate must block a whole-suite pass-claim over a live lastfailed record"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "tests/t.py::test_red" in decision["reason"]


def test_dispatch_unpaid_acceptance_gate_blocks_when_acceptance_never_ran(tmp_path):
    """Behavioral blocking pin for gate.unpaid_acceptance through the real dispatch: a dispatch's
    ACCEPTANCE never ran, the dispatch is from BEFORE the operator's current turn (a transcript
    user turn after it establishes that boundary — see the gate's own in-flight exclusion), and
    the tree opts in via makoto.toml `dispatch = true` -> BLOCK."""
    state_dir = _setup_state(tmp_path)
    (tmp_path / "makoto.toml").write_text("dispatch = true\n")
    dispatch = {
        "hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "unpaid",
        "cwd": str(tmp_path),
        "tool_input": {
            "description": "fix",
            "prompt": ("READ: plugin/makoto/kit.py@3f2a9c1e0b7d\n"
                       "WRITE: plugin/makoto/kit.py\n"
                       "ACCEPTANCE: python3 -m pytest -q tests/test_kit.py\n"
                       "Fix the off-by-one in unwitnessed."),
        },
    }
    rc, out = _run_dispatch(state_dir, dispatch)
    assert rc == 0
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(json.dumps({
        "type": "user", "timestamp": now,
        "message": {"role": "user", "content": "status?"},
    }) + "\n")
    stop = {"hook_event_name": "Stop", "session_id": "unpaid", "cwd": str(tmp_path),
            "transcript_path": str(transcript),
            "last_assistant_message": "Done: the off-by-one is fixed."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "unpaid_acceptance gate must block a dispatch whose ACCEPTANCE never ran"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "ACCEPTANCE" in decision["reason"]


def test_dispatch_self_wired_gate_blocks_when_it_fires(tmp_path):
    """Behavioral pin for gate.self_wired's ONE deliberate exception to discovered<=>live<=>blocking
    (2026-07-05, DESIGN DECISION): it IS discovered (reaching the decision pipeline like every other
    gate) and its predicate DOES fire on a partial hook-wiring strip, but it ships at
    level="advisory" (never "error"), so _build_decision's error-only filter must never turn this
    fire into a block. This is the behavioral counterpart to
    test_every_blocking_gate_has_a_behavioral_dispatch_block_test's documented exemption for
    gate.self_wired below (that test cannot require a "...gate_blocks" test for an id that
    structurally never blocks); this test instead pins the opposite claim end-to-end — fires
    (audited) AND never blocks — through the real dispatch path."""
    state_dir = _setup_state(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto.dispatch"}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto.dispatch"}]}],
        # Stop entry deliberately absent -> a partial strip -> gate.self_wired fires, advisory only.
    }}))
    stop = {"hook_event_name": "Stop", "session_id": "sw", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "gate.self_wired must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.self_wired" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.self_wired" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited so a partial strip leaves a forensic trail"


def test_dispatch_plan_item_drift_gate_blocks_when_it_fires(tmp_path):
    """gate.plan_item_drift (F8, BLOCK since 2026-09-25): a plan/task-labeled commitment left open
    blocks every stop that finds it open, and saying it is done discharges it."""
    state_dir = _setup_state(tmp_path)
    first = {"hook_event_name": "Stop", "session_id": "planitem", "cwd": str(tmp_path),
             "last_assistant_message": "I'll finish §9.3 after this push."}
    rc, out = _run_dispatch(state_dir, first)
    assert out, "gate.plan_item_drift must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.plan_item_drift" in decision["reason"]
    second = {"hook_event_name": "Stop", "session_id": "planitem", "cwd": str(tmp_path),
              "last_assistant_message": "Moving on to other work for now."}
    rc, out = _run_dispatch(state_dir, second)
    assert "gate.plan_item_drift" in json.loads(out)["reason"], "still open, still blocks"
    rc, out = _run_dispatch(state_dir, dict(second, last_assistant_message="I finished §9.3."))
    assert "gate.plan_item_drift" not in out, "saying it is done discharges it"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert sum("gate.plan_item_drift" in r.get("pattern_fires", []) for r in rows) == 2, \
        "the fire must be audited so it leaves a forensic trail"


def _post_bash(tmp_path, session, command, stdout=""):
    return {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
            "tool_name": "Bash", "tool_input": {"command": command},
            "tool_response": {"stdout": stdout, "exitCode": 0}}


def test_dispatch_unread_structure_gate_blocks_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.unread_structure (2026-09-18) fires
    (audited) and blocks (BLOCK since 2026-09-25) when its own condition holds -- a jq traversal that printed `null` with no structure read before it."""
    state_dir = _setup_state(tmp_path)
    _run_dispatch(state_dir, _post_bash(tmp_path, "unread_struct", "jq '.a.b' config.json", "null"))
    stop = {"hook_event_name": "Stop", "session_id": "unread_struct", "cwd": str(tmp_path),
            "last_assistant_message": "Done."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "gate.unread_structure must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.unread_structure" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.unread_structure" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited so it leaves a forensic trail"


def test_dispatch_unwitnessed_verifier_gate_blocks_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.unwitnessed_verifier (2026-09-18) fires
    (audited) and blocks (BLOCK since 2026-09-25) when its own condition holds -- a first clean verifier run with no red run ever seen."""
    state_dir = _setup_state(tmp_path)
    _run_dispatch(state_dir, _post_bash(tmp_path, "unwitnessed", "pytest -q", "58 passed in 2.0s"))
    stop = {"hook_event_name": "Stop", "session_id": "unwitnessed", "cwd": str(tmp_path),
            "last_assistant_message": "Done."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "gate.unwitnessed_verifier must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.unwitnessed_verifier" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.unwitnessed_verifier" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited so it leaves a forensic trail"


def test_dispatch_unnamed_failure_gate_blocks_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.unnamed_failure (2026-09-18,
    register C12) blocks (BLOCK since 2026-09-25) and is audited when its own condition holds -- a turn
    that counts a failure while the run's own recorded identity goes unnamed."""
    state_dir = _setup_state(tmp_path)
    _run_dispatch(state_dir, _post_bash(
        tmp_path, "unnamed", "python3 -m pytest -q",
        stdout="tests/test_a.py::test_charge FAILED\n1 failed in 1.0s"))
    stop = {"hook_event_name": "Stop", "session_id": "unnamed", "cwd": str(tmp_path),
            "last_assistant_message": "1 test failed; looking into it."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "gate.unnamed_failure must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.unnamed_failure" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.unnamed_failure" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited so it leaves a forensic trail"


def test_dispatch_unclaimed_unit_gate_blocks_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.unclaimed_unit (2026-09-18,
    register H6) blocks (BLOCK since 2026-09-25) and is audited when its own condition holds -- a
    top-level function written that nothing reaches and no decorator registered."""
    state_dir = _setup_state(tmp_path)
    _run_dispatch(state_dir, {"hook_event_name": "PostToolUse", "session_id": "unclaimed",
                              "cwd": str(tmp_path), "tool_name": "Write",
                              "tool_input": {"file_path": "src/helpers.py",
                                             "content": "def helper(a):\n    return a + 1\n"},
                              "tool_response": {}})
    stop = {"hook_event_name": "Stop", "session_id": "unclaimed", "cwd": str(tmp_path),
            "last_assistant_message": "Added a helper."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "gate.unclaimed_unit must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.unclaimed_unit" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.unclaimed_unit" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited so it leaves a forensic trail"


def test_dispatch_pasted_fix_gate_blocks_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.pasted_fix (2026-09-18, register
    H3) blocks (BLOCK since 2026-09-25) and is audited when its own condition holds -- one repair's
    text edited into a second file with no verifier run between the two landings."""
    state_dir = _setup_state(tmp_path)
    repair = ("if timeout is None:\n"
              "    timeout = DEFAULT_TIMEOUT\n"
              "if timeout < 0:\n"
              "    raise ValueError(timeout)\n")
    for path in ("src/reader.py", "src/writer.py"):
        _run_dispatch(state_dir, {"hook_event_name": "PostToolUse", "session_id": "pasted",
                                  "cwd": str(tmp_path), "tool_name": "Edit",
                                  "tool_input": {"file_path": path, "old_string": "pass",
                                                 "new_string": repair},
                                  "tool_response": {}})
    stop = {"hook_event_name": "Stop", "session_id": "pasted", "cwd": str(tmp_path),
            "last_assistant_message": "Fixed both readers."}
    rc, out = _run_dispatch(state_dir, stop)
    assert out, "gate.pasted_fix must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.pasted_fix" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.pasted_fix" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited so it leaves a forensic trail"


def test_no_shadow_gate_every_gate_blocks():
    """Warning-tier-elimination invariant, STRUCTURAL after the gates/ package cutover: every
    check discovered at the Stop edge reaches the decision pipeline (no audit-only shadow tier)
    -- `load_checks(edge="Stop")` IS the pipeline-eligible set, with no separate filter to fall
    out of. The former check.quantity shadow gate was CUT 2026-06-02 — it could not block
    FP-safely. A future shadow gate (discoverable but never wired into run_stop_checks) turns
    this red."""
    from makoto.registry import load_checks
    live = load_checks(edge="Stop")
    discovered = {c.id for c in live}
    assert discovered == {"gate.completion", "gate.green_claim", "gate.dropped",
                          "gate.fabricated_action", "gate.named_test", "gate.stale_pass",
                          "gate.liveness",     # liveness folded in from the collapsed close-check tier
                          "gate.hollow_test",  # HOLLOWED-class detector (SPIRIT.md §4), same split as liveness
                          "gate.canon",        # ported agnostic Stop primitives canon.timeout/canon.recur
                          "gate.canon_fingerprints",            # SPEC-5 Task 9: BLOCK-tier canon fingerprints
                          "gate.self_wired",   # B1/B26/D9, BLOCK since 2026-09-25
                          "gate.plan_item_drift",         # F8, BLOCK since 2026-09-25
                          "gate.claimed_running",  # agnostic claim-vs-recorded-Bash-evidence gate (2026-07-23)
                          "gate.claimed_shipped",  # completed remote-mutation claim-vs-record gate
                          "gate.claimed_consent_absent",
                          "gate.unexamined_wall",   # register G5's runner
                          "gate.unread_structure",     # A3: the latest traversal only
                          "gate.unwitnessed_verifier",  # B4
                          "gate.run_promised",       # C11: a promised run with no Bash since
                          "gate.unnamed_failure",      # C12
                          "gate.unclaimed_unit",       # H6
                          "gate.pasted_fix",           # H3 (and F2)
                          "gate.undeclared_falsifiable",  # B32/C2: catalog-completeness auditor
                          "gate.unworded_close",       # G1, opt-in words_file
                          "gate.unrun_count_claim",    # C11: a counted all-pass with no run
                          "gate.unpaid_acceptance"}    # PROPOSED-REGISTER-ROWS.md I3's runner,
                                               # opt-in (makoto.toml `dispatch = true`)
    # The check.quantity / claim_check capability no longer EXISTS: no live gate's run adapter
    # references it, and the package exposes no such callable (re-adding it as a gate turns this
    # red). No separate `.fn` attribute anymore (GATE/StopCheck retired) -- introspect the actual
    # function names each `run` closure/adapter references via its code object.
    referenced = {name for c in live for name in c.run.__code__.co_names}
    assert "claim_check" not in referenced
    assert "dropped_gate" in referenced       # live -> discovered + reaches the pipeline


def test_dispatch_undeclared_falsifiable_gate_blocks_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.undeclared_falsifiable (the
    catalog-completeness auditor) fires (audited) but never blocks -- it ships at
    level="advisory" like every other named ADVISE exception here.

    Unlike every other gate, its `run` ignores GateContext and audits the REAL checks/ package
    on disk, so this plants a genuine orphan module into the real package for the one dispatch
    call and removes it in `finally`, whatever the outcome."""
    state_dir = _setup_state(tmp_path)
    checks_dir = Path(__file__).resolve().parent.parent / "plugin" / "makoto" / "checks"
    orphan = checks_dir / "zz_test_orphan_probe.py"
    orphan.write_text("VALUE = 1\n")
    try:
        stop = {"hook_event_name": "Stop", "session_id": "uf", "cwd": str(tmp_path),
                "last_assistant_message": "Done for now."}
        rc, out = _run_dispatch(state_dir, stop)
    finally:
        orphan.unlink(missing_ok=True)
    assert out, "gate.undeclared_falsifiable must block the stop when it fires"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.undeclared_falsifiable" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.undeclared_falsifiable" in r.get("pattern_fires", []) for r in rows), \
        "the fire must be audited so it leaves a forensic trail"


def test_every_blocking_gate_has_a_behavioral_dispatch_block_test():
    """Gap-CLASS closer (generalizes the gate.dropped miss). The set-equality pin above is STRUCTURAL:
    dropping a gate from the catalog reddens it, but so would a legitimate addition — it pins
    the set's value, not the gate's blocking BEHAVIOR. The behavioral pin is a dispatch test that
    drives a triggering Stop message all the way through `_run_dispatch` and asserts decision==block.
    gate.dropped shipped without one — so require every BLOCK-posture gate to carry a
    `test_dispatch_<gate>_gate_blocks*` test, by the same naming convention its siblings already
    follow. A future blocking gate added without one reddens HERE, at landing, instead of leaving
    its real blocking behavior unfalsifiable.

    Since 2026-09-25 no Stop gate is ADVISE (tests/test_stop_gate_level_invariant.py pins it),
    so every one needs its block test."""
    from pathlib import Path as _P
    from makoto.registry import POSTURE_ADVISE, load_checks
    stop_checks = load_checks(edge="Stop")
    _ADVISORY_EXEMPT = {c.id for c in stop_checks if c.posture == POSTURE_ADVISE}
    # A NAME IS NOT A TEST. This searched the source for `def test_dispatch_<name>_gate_blocks`,
    # so an empty function with the right name -- or one that asserts nothing, or never reaches
    # the dispatcher -- satisfied a law whose whole subject is BEHAVIOURAL coverage. The name is
    # still how the test is found, but the function it names must now be parsed and required to
    # do the two things the law is about: drive the dispatcher, and assert on what came back.
    import ast as _ast
    tree = _ast.parse(_P(__file__).read_text())
    named = {}
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            named.setdefault(node.name, node)

    missing, hollow = [], []
    for gid in sorted(c.id for c in stop_checks):
        if gid in _ADVISORY_EXEMPT:
            continue
        prefix = f"test_dispatch_{gid.split('.')[-1]}_gate_blocks"
        found = [name for name in named if name.startswith(prefix)]
        if not found:
            missing.append(gid)
            continue
        # At least one of the tests bearing this name must both call the dispatcher and assert.
        def _drives_and_asserts(fn):
            """Drove the dispatcher AND asserted on what came back.

            `any assert` was the previous bar, so `_run_dispatch(...)` followed by
            `assert True` satisfied a law about behavioural coverage. An assertion has to
            mention something the dispatch produced: a name bound from a driver call, or the
            call's result used directly.
            """
            drivers = {n for n in _ast.walk(fn)
                       if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
                       and n.func.id in _DISPATCH_DRIVERS}
            if not drivers:
                return False
            # Names bound from a driver call: `out = _run_dispatch(...)`, `rc, out = ...`.
            produced = set()
            for node in _ast.walk(fn):
                if isinstance(node, _ast.Assign) and isinstance(node.value, _ast.Call) \
                        and isinstance(node.value.func, _ast.Name) \
                        and node.value.func.id in _DISPATCH_DRIVERS:
                    for target in node.targets:
                        for piece in _ast.walk(target):
                            if isinstance(piece, _ast.Name):
                                produced.add(piece.id)
            # An assertion has to be ABOUT THE BLOCK, not merely about the produced value.
            # `assert result is not None` mentions it and says nothing about blocking, which is
            # the claim this law makes; every real test here asserts on the decision, its
            # "block" verdict, or the reason text. Anything derived from the produced value is
            # accepted -- `decision = json.loads(out)` then `assert decision["decision"] ==
            # "block"` -- by following assignments transitively from the driver's result.
            derived = set(produced)
            for _pass in range(4):          # a fixed point over the short chains these tests use
                for node in _ast.walk(fn):
                    if isinstance(node, _ast.Assign):
                        mentioned = {n.id for n in _ast.walk(node.value)
                                     if isinstance(n, _ast.Name)}
                        if mentioned & derived:
                            for target in node.targets:
                                for piece in _ast.walk(target):
                                    if isinstance(piece, _ast.Name):
                                        derived.add(piece.id)
            for node in _ast.walk(fn):
                if not isinstance(node, _ast.Assert):
                    continue
                names = {n.id for n in _ast.walk(node) if isinstance(n, _ast.Name)}
                touches_result = bool(names & derived) or any(
                    isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
                    and n.func.id in _DISPATCH_DRIVERS for n in _ast.walk(node))
                if not touches_result:
                    continue
                text = _ast.dump(node)
                if "'block'" in text or '"block"' in text or "block" in names \
                        or "decision" in text or "reason" in text:
                    return True
            return False
        if not any(_drives_and_asserts(named[name]) for name in found):
            hollow.append(f"{gid} -> {sorted(found)}")

    assert not missing, (f"blocking gate(s) without a BEHAVIORAL dispatch-block test (a structural "
                         f"set-membership pin is not enough — see this test's docstring): {missing}")
    assert not hollow, (
        f"these gates have a correctly NAMED dispatch-block test that never drives the "
        f"dispatcher, or never asserts that it BLOCKED -- `assert True`, or `assert result is "
        f"not None`, after a dispatch call is not coverage of blocking, so the name is the only "
        f"evidence: {hollow}")


# ---------------------------------------------------------------------------
# Line-level pinning tests (mutation-audit gap closure for dispatch.py).
# Each test below reddens a specific surviving single-token mutant; the
# (lineno, kind) it closes is named in the docstring.
# ---------------------------------------------------------------------------


def test_dispatch_lazy_init_success_propagates_so_firing_event_blocks(tmp_path):
    """Pins line 62 (`_ensure_db_initialized` success -> `return True`), RETURN and CONST.

    On the lazy-init path (db absent), a successful init MUST return truthy so main()
    does NOT fail open at line 250. A firing PreToolUse event (content.verifier_predicate_weakened, loose
    comparator in a verifier file) created via lazy init must still emit block JSON.
    If `return True` is mutated to `return None`/`return False`, main() fails open and
    stdout is empty -> this assertion reddens.
    """
    state_dir = tmp_path / "makoto_state"
    state_dir.mkdir(parents=True)  # dir exists, but NO makoto.record.db -> dispatcher inits lazily
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "lazy_init_fire",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "constitution/integrity/checks/v.py",
            "content": 'def check(s):\n    return s.startswith("ok")\n',
        },
    }
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto.dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent / "plugin"),
    )
    assert proc.returncode == 0
    out = proc.stdout.decode("utf-8")
    assert (state_dir / "makoto.record.db").is_file(), "lazy init should have created makoto.record.db"
    assert out, "lazy-init success must propagate so the firing event still blocks (not fail-open)"
    decision = json.loads(out)
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_dispatch_lazy_init_failure_fails_open_not_crash(tmp_path):
    """Pins line 65 (`_ensure_db_initialized` except handler -> `return False`), RETURN and CONST.

    When lazy init RAISES (here: state_dir already exists as a regular file, so db creation
    fails), the handler must return falsy so main() fails open at line 250 (exit 0, no crash).
    If `return False` is mutated to `return True`, main() skips the fail-open guard and
    _connect_with_retry hits a non-existent db -> unhandled sqlite3.OperationalError -> the
    process exits non-zero. This asserts the fail-open contract (rc == 0).
    """
    state_dir = tmp_path / "makoto_state"
    state_dir.write_text("i am a regular file, not a directory\n")  # makes init_db raise
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "init_fail",
        "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/x.txt", "content": "hello"},
    }
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto.dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent / "plugin"),
    )
    assert proc.returncode == 0, (
        "lazy-init failure must fail OPEN (exit 0), never crash the hook; "
        f"got rc={proc.returncode}, stderr={proc.stderr.decode('utf-8')!r}"
    )
    # "No DECISION" is the invariant, and it still holds. What a failed-open dispatch now DOES
    # emit is a `systemMessage` notice, because a fail-open whose only trace is stderr is
    # invisible to the user, the model and the transcript alike.
    out = proc.stdout.decode("utf-8")
    assert "permissionDecision" not in out and '"decision"' not in out, (
        f"a failed-open dispatch must emit no decision; got {out!r}")
    assert "ALLOWED WITHOUT BEING CHECKED" in json.loads(out)["systemMessage"]


def test_connect_with_retry_sleeps_backoff_between_attempts(monkeypatch):
    """Pins line 89 (`if attempt < _LOCK_RETRY_ATTEMPTS - 1:` guarding the backoff sleep), NOT and CMP.

    Under sustained lock contention, the dispatcher backs off between every attempt EXCEPT the
    last -> exactly (_LOCK_RETRY_ATTEMPTS - 1) sleeps. Negating the test (NOT) sleeps only on the
    last attempt (1 sleep); swapping the comparator `<`->`>` (CMP) never sleeps (0 sleeps). Either
    mutation changes the observed sleep count, so pinning it to ATTEMPTS-1 reddens both.
    """
    import sqlite3
    from makoto import dispatch
    sleeps = {"n": 0}

    def _locked(*a, **kw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", _locked)
    monkeypatch.setattr(dispatch.time, "sleep", lambda _s: sleeps.__setitem__("n", sleeps["n"] + 1))
    assert dispatch._connect_with_retry(Path("/tmp/whatever.db")) is None
    assert sleeps["n"] == dispatch._LOCK_RETRY_ATTEMPTS - 1, (
        "backoff must sleep between every attempt except the last "
        f"(expected {dispatch._LOCK_RETRY_ATTEMPTS - 1}, got {sleeps['n']})"
    )


def test_keyword_hit_empty_keywords_returns_false():
    """Pins line 122 (`if not pattern.keywords: return False`), RETURN and CONST.

    A pattern with no keywords matches nothing — the guard must return False. Mutating
    `return False` to `return None`/`return True` makes an empty-keyword pattern (synthetic,
    a defensive branch) claim a hit on any payload. Direct unit on the helper.
    """
    from makoto.dispatch import _keyword_hit
    from makoto.vocab import PreCheck
    pattern = PreCheck(id="x", description="d", fire_level="error",
                      predicate_module="m", keywords=[], retry_hint="")
    assert _keyword_hit(pattern, "any payload at all") is False


def test_keyword_hit_all_keywords_present_returns_true():
    """Pins line 123 (`return any(kw in raw_payload for kw in pattern.keywords)`), CMP (`in`->`not in`).

    With EVERY keyword present in the payload, the prefilter must report a hit. The `in`->`not in`
    swap turns `any(kw in payload)` into `any(kw not in payload)`, which is False precisely when
    all keywords are present -> the hit is lost. Asserting True on an all-present payload reddens
    the swap (a partial-present payload would not, since `not in` is True for the missing kw).
    """
    from makoto.dispatch import _keyword_hit
    from makoto.vocab import PreCheck
    pattern = PreCheck(id="y", description="d", fire_level="error",
                      predicate_module="m", keywords=["foo", "bar"], retry_hint="")
    assert _keyword_hit(pattern, "xx foo yy bar zz") is True


def test_dispatch_select_recent_returns_history_so_history_predicate_fires(tmp_path):
    """Pins line 110 (`_select_recent` -> `return conn.execute(...).fetchall()`), RETURN.

    A history-walking predicate (content.fabricated_commit_sha: fabricated commit SHA) needs the real prior-event slice.
    A Stop claiming a commit SHA with no prior `git commit` tool_use fires content.fabricated_commit_sha and blocks.
    If `_select_recent` returns None instead of the list, `for entry in history` raises TypeError
    inside the predicate, which dispatch swallows -> content.fabricated_commit_sha never fires -> no block JSON. Asserting
    the block fires pins the real return value.
    """
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "fab_sha",
        "cwd": str(tmp_path),
        "last_assistant_message": "Committed the fix in abc1234. Done.",
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "content.fabricated_commit_sha (fabricated SHA) must fire on a real history slice -> block JSON"
    assert json.loads(out)["decision"] == "block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("content.fabricated_commit_sha" in r.get("pattern_fires", []) for r in rows), \
        "the content.fabricated_commit_sha fire must be recorded (history slice was actually returned)"


def test_dispatch_fabricated_commit_sha_catches_shipped_reword(tmp_path):
    """Same fabricated-evidence claim as "committed as <sha>", reworded with "shipped" -- a
    completion verb outside the check's own committed/tag/landed/pushed/merged/created/made
    vocabulary must still fire content.fabricated_commit_sha itself, not just the sibling
    gate.claimed_shipped."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "fab_sha_shipped",
        "cwd": str(tmp_path),
        "last_assistant_message": "Shipped it at a1b2c3d4e5f6 on main.",
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "content.fabricated_commit_sha must fire on the 'shipped' reword"
    assert json.loads(out)["decision"] == "block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("content.fabricated_commit_sha" in r.get("pattern_fires", []) for r in rows), \
        "the content.fabricated_commit_sha fire must be recorded for the 'shipped' reword"


def test_dispatch_unsourced_webfetch_catches_mcp_fetch_tool(tmp_path):
    """Same fabricated-url defect as a bare WebFetch, but fetched by a differently-named MCP
    tool (`mcp__browser__fetch`). The check must recognize a fetch-shaped tool by its `url`
    input, not only the literal tool name "WebFetch"."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__browser__fetch",
        "session_id": "webfetch_mcp",
        "cwd": str(tmp_path),
        "tool_input": {"url": "https://docs-internal-vendorzzz.example.net/api/reference"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "content.unsourced_webfetch must fire on an unsourced url fetched via an MCP fetch tool"
    decision = json.loads(out)
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("content.unsourced_webfetch" in r.get("pattern_fires", []) for r in rows), \
        "the content.unsourced_webfetch fire must be recorded for the MCP fetch tool"


def test_dispatch_decision_carries_retry_hint_when_finding_has_one(tmp_path):
    """PreCheck content.verifier_predicate_weakened produces a truthy retry_hint (via `_jit_hint`). SPEC-5 Task 8: the live
    decision JSON no longer has a separate top-level "retry_hint" key -- `_emit_decision` folds
    the JIT hint (the pattern's own retry_hint text + the makoto-allow hatch + the conventions
    pointer) into the finding's message as the wire Decision's `.detail`, which wire.py's
    `_pre_permission` surfaces as `permissionDecisionReason`. Asserting the hint text is present there
    pins that the fold still happens (a dropped hint would silently lose all retry guidance).
    """
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "hint_test",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "/tmp/constitution/integrity/checks/v.py",
            "content": 'def check(s): return s.startswith("ok")\n',
        },
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert out, "content.verifier_predicate_weakened must emit a block decision"
    decision = json.loads(out)
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Use '=='" in reason, (
        "a finding's retry_hint text must surface in the emitted permissionDecisionReason "
        "(the JIT hint must not be silently dropped in the posture fold)"
    )
    assert "MAKOTO-CONVENTIONS.md" in reason, "every block must still point at the conventions"


def test_dispatch_audit_exit_code_is_2_on_error_level_finding(tmp_path):
    """Pins line 234 (`exit_code=(2 if any(f.level == "error" ...) else 0)`), CMP (`==`->`!=`).

    PreCheck content.verifier_predicate_weakened is an error-level finding, so the recorded audit row's exit_code must be 2.
    Swapping `==` to `!=` computes exit_code from non-error findings -> records 0 instead.
    Asserting the recorded exit_code == 2 pins the comparator.
    """
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "exit_code_test",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "/tmp/constitution/integrity/checks/v.py",
            "content": 'def check(s): return s.startswith("ok")\n',
        },
    }
    rc, _ = _run_dispatch(state_dir, payload)
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert rows, "the error-level fire must record an audit row"
    fire_rows = [r for r in rows if "content.verifier_predicate_weakened" in r.get("pattern_fires", [])]
    assert fire_rows, "expected a content.verifier_predicate_weakened fire row"
    assert fire_rows[0].get("exit_code") == 2, (
        "an error-level finding must record exit_code=2 in the audit row; "
        f"got {fire_rows[0].get('exit_code')!r}"
    )


# --- regressions found by an independent high-effort review pass ------------------------------

def test_a_failing_error_logger_does_not_abandon_the_remaining_checks(tmp_path, monkeypatch):
    """Observability must never decide a verdict, and here it did -- in the worst direction.

    `audit.append_error` on a predicate's ERROR path was unguarded, so an append that raised
    escaped `_run_predicates` entirely: every pattern after the raising one went unevaluated, and
    the unwind landed in `_dispatch`'s catch-all, which records a loud-allow and returns 0. A
    later predicate that would have DENIED simply never ran. A failure in the error LOGGER turned
    a deny into an allow.
    """
    import types
    from makoto import dispatch as D
    from makoto.state import audit as A
    from makoto.vocab import Finding

    ran = []
    boom = types.ModuleType("mk_boom")
    def _boom(**_kw):
        ran.append("boom")
        raise RuntimeError("predicate exploded")
    boom.predicate = _boom
    denier = types.ModuleType("mk_denier")
    def _deny(**_kw):
        ran.append("denier")
        return Finding(pattern_id="x.deny", file="f.py", line=1, level="error",
                       message="would have DENIED", snippet="")
    denier.predicate = _deny
    monkeypatch.setitem(sys.modules, "mk_boom", boom)
    monkeypatch.setitem(sys.modules, "mk_denier", denier)

    class P:
        def __init__(self, i, m):
            self.id, self.predicate_module = i, m
    monkeypatch.setattr(D, "load_precheck_catalog",
                        lambda: [P("x.boom", "mk_boom"), P("x.deny", "mk_denier")])
    monkeypatch.setattr(D, "_keyword_hit", lambda p, raw: True)
    monkeypatch.setattr(D, "_disabled_pattern_ids", lambda: set())
    monkeypatch.setattr(A, "append_error",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("ledger disk full")))

    findings = D._run_predicates(None, {"session_id": "s"}, [], 1, tmp_path, "raw")
    assert ran == ["boom", "denier"], f"the later check never ran: {ran}"
    assert [f.pattern_id for f in findings] == ["x.deny"], "the DENY was lost"


def test_a_failed_decision_write_is_reported_rather_than_silently_dropped(tmp_path):
    """Two of these fixes collided here, and this test records how the collision was settled.

    The wire claim was moved BEFORE the write so a half-written decision could not be followed by
    a whole second JSON object. Then a review pass showed the same claim silenced the notice when
    the write failed having emitted NOTHING -- the DENY reached nobody, the notice reached nobody,
    and an unchecked call looked like a clean pass.

    The two cannot both be satisfied, because a raised `write` does not say how many bytes landed.
    So the trade is made deliberately: when the decision write FAILS, the notice is emitted. A
    fragment on stdout is unparseable whether or not something follows it, so the notice cannot
    turn a good response into a bad one -- while suppressing it loses the only signal that says a
    check did not decide anything. The claim still does its original job on the path that matters:
    a decision that was written SUCCESSFULLY is never followed by a notice.
    """
    from makoto import dispatch as D
    from makoto.vocab import Finding

    # ONE stream for the decision AND the notice, because in production there is only one: the
    # earlier version handed `_emit_decision` a private object and then pointed `sys.stdout` at a
    # fresh buffer, so it asserted a notice was PRODUCED while never showing what the wire ends up
    # holding. That is the only question this trade turns on.
    class HalfDeadStream:
        """First write keeps 12 characters and raises; later writes land. A disk that filled and
        was freed, an EINTR -- the case where the notice actually reaches the wire behind the
        fragment, which is the case the trade has to be judged on."""

        def __init__(self):
            self.written = ""
            self.calls = 0

        def write(self, s):
            self.calls += 1
            if self.calls == 1:
                self.written += s[:12]
                raise BrokenPipeError("pipe closed mid-write")
            self.written += s
            return len(s)

    class DeadStream:
        def write(self, s):
            raise BrokenPipeError("pipe closed for good")

    saved = (D._stdout_written, list(D._notices), D._decision_write_failed)
    finding = Finding(pattern_id="content.x", file="f.py", line=1, level="error",
                      message="denied", snippet="")

    class GoodStream:
        def __init__(self):
            self.written = ""

        def write(self, s):
            self.written += s
            return len(s)

    try:
        # 1. a SUCCESSFUL decision still shuts the notice emitter up, on the SAME stream.
        D._stdout_written, D._decision_write_failed = False, False
        D._notices[:] = ["[db_locked] write lock not acquired"]
        good = GoodStream()
        D._emit_decision([finding], "PreToolUse", stream=good)
        delivered = good.written
        real, sys.stdout = sys.stdout, good
        try:
            D._emit_notices()
        finally:
            sys.stdout = real
        assert good.written == delivered, "a notice was appended behind a delivered decision"
        assert json.loads(good.written)["hookSpecificOutput"], "the decision is not intact JSON"

        # 2. a FAILED decision write is reported instead -- and this is what the wire then holds.
        D._stdout_written, D._decision_write_failed = False, False
        D._notices[:] = ["[db_locked] write lock not acquired"]
        stream = HalfDeadStream()
        with pytest.raises(BrokenPipeError):
            D._emit_decision([finding], "PreToolUse", stream=stream)
        assert D._stdout_written is True
        assert D._decision_write_failed is True
        fragment = stream.written
        assert fragment == '{"hookSpecif', f"unexpected fragment: {fragment!r}"
        real, sys.stdout = sys.stdout, stream
        try:
            D._emit_notices()
        finally:
            sys.stdout = real
        assert "systemMessage" in stream.written, "the undelivered decision was never reported"
        # The trade, asserted rather than asserted-around: the wire now carries the fragment with
        # the notice behind it, and that is NOT parseable. It was not parseable before the notice
        # either -- a 12-character fragment never is -- so the notice destroys nothing and is the
        # only thing on the wire that explains why no decision arrived. Written down as a test so
        # the cost is visible to whoever revisits this, instead of living in a comment.
        with pytest.raises(ValueError):
            json.loads(stream.written)
        assert stream.written.startswith(fragment)

        # 3. a stream that is dead for good: the notice cannot land, and must not raise either.
        D._stdout_written, D._decision_write_failed = False, False
        D._notices[:] = ["[db_locked] write lock not acquired"]
        dead = DeadStream()
        with pytest.raises(BrokenPipeError):
            D._emit_decision([finding], "PreToolUse", stream=dead)
        real, sys.stdout = sys.stdout, dead
        try:
            D._emit_notices()          # must swallow: reporting never outranks returning
        finally:
            sys.stdout = real
    finally:
        D._stdout_written, D._notices[:], D._decision_write_failed = saved[0], saved[1], saved[2]


def test_a_prologue_fault_is_a_loud_allow_not_a_crash(tmp_path, monkeypatch, capsys):
    """`_dispatch` wraps only the HANDLER, so its whole prologue ran with no catch, and `main`'s
    `finally` does not absorb -- it re-raises. A fault in the stdin read, the state-dir resolve,
    the parse or the chain self-verify left the hook with a traceback and a non-zero exit instead
    of the loud-allow that IS this plugin's declared fail direction for carriage faults.
    """
    from makoto import dispatch as D
    monkeypatch.setattr(D.wire, "read_stdin",
                        lambda: (_ for _ in ()).throw(RuntimeError("carriage exploded")))
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path))
    assert D.main() == 0
    err = capsys.readouterr()
    assert "prologue_exception" in err.err
    assert "carriage exploded" in err.err


def test_a_decision_that_never_reached_the_wire_still_reports_the_fault(tmp_path):
    """Found by an independent review pass, against the previous fix.

    Claiming the wire before the write closed the fragment-plus-second-object corruption, but it
    also claimed the wire when the write raised having emitted NOTHING -- EPIPE on the first byte,
    a closed fd. Then the DENY reached nobody AND the notice was suppressed, so a call that was
    never decided looked exactly like a clean pass. The claim must not silence the report when
    there is nothing on the wire to protect.
    """
    from makoto import dispatch as D
    from makoto.vocab import Finding

    class RejectsOutright:
        """Rejects the first write having emitted NOTHING, then accepts. One object, used for the
        decision AND the notice, because pointing `sys.stdout` at a fresh buffer for the second
        call proved only that a notice was ATTEMPTED -- on a stream that was still dead it could
        not have landed, and the test's name promises it reaches the wire."""

        def __init__(self):
            self.written = ""
            self.calls = 0

        def write(self, s):
            self.calls += 1
            if self.calls == 1:
                raise BrokenPipeError("rejected before any byte was written")
            self.written += s
            return len(s)

    saved = (D._stdout_written, list(D._notices), D._decision_write_failed)
    D._stdout_written, D._decision_write_failed = False, False
    D._notices[:] = ["[db_locked] write lock not acquired"]
    try:
        finding = Finding(pattern_id="content.x", file="f.py", line=1, level="error",
                          message="denied", snippet="")
        stream = RejectsOutright()
        with pytest.raises(BrokenPipeError):
            D._emit_decision([finding], "PreToolUse", stream=stream)
        assert stream.written == "", "the decision was supposed to reach nobody"
        real, sys.stdout = sys.stdout, stream
        try:
            D._emit_notices()
        finally:
            sys.stdout = real
        assert stream.written, "the call was never decided and nobody was told"
        assert "systemMessage" in stream.written
        # Zero bytes of decision landed, so unlike the half-written case there is no fragment in
        # front of the notice: the wire carries ONE valid object, and it is the one that says the
        # call went undecided.
        assert json.loads(stream.written)["systemMessage"]
    finally:
        D._stdout_written, D._notices[:], D._decision_write_failed = saved[0], saved[1], saved[2]


def test_main_does_not_inherit_the_previous_calls_notices(tmp_path, monkeypatch, capsys):
    """`_notices` and `_stdout_written` are module globals. A second `main()` in one interpreter
    re-reported the first call's faults under the wrong event and grew the list without bound."""
    from makoto import dispatch as D
    monkeypatch.setattr(D.wire, "read_stdin",
                        lambda: (_ for _ in ()).throw(RuntimeError("carriage exploded")))
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path))
    D.main()
    capsys.readouterr()
    D.main()
    assert len(D._notices) == 1, f"notices accumulated across calls: {D._notices!r}"


def test_every_stop_gate_finding_reaches_the_decision(monkeypatch, capsys, state_dir):
    """Every Stop-edge check's finding reaches `_emit_decision`, OBSERVED (not just asserted by
    set comparison) -- there is no filter left in `_evaluate_and_gate` between `run_stop_checks`
    and `_emit_decision`; a check's `.posture` alone decides whether the fold turns it into an
    actual block. This drives a planted Finding through `_evaluate_and_gate` itself and requires
    it to actually produce a decision."""
    import json as _json
    import sqlite3
    from makoto import dispatch as D
    from makoto.registry import load_checks

    any_gate = sorted(c.id for c in load_checks(edge="Stop"))
    assert any_gate, "no Stop check discovered; the check below would be vacuous"

    payload = {"hook_event_name": "Stop", "session_id": "stop-gate-roundtrip",
               "cwd": str(state_dir), "last_assistant_message": "done"}

    def drive(pattern_id):
        planted = D.Finding(pattern_id=pattern_id, file="x.py", line=1, level="error",
                            message="planted", retry_hint="")
        monkeypatch.setattr(D, "run_stop_checks", lambda *a, **k: [planted])
        monkeypatch.setattr(D, "_gates_enabled", lambda *a, **k: True)
        conn = sqlite3.connect(str(state_dir / "makoto.record.db"), isolation_level=None)
        try:
            capsys.readouterr()
            D._evaluate_and_gate(conn, payload, _json.dumps(payload), 1, state_dir)
        finally:
            conn.close()
        return capsys.readouterr().out

    assert drive(any_gate[0]), (
        f"{any_gate[0]}'s finding produced no decision through _evaluate_and_gate; every "
        f"Stop-edge finding must reach it now")




def _pre(tmp_path, sid, tool, **ti):
    return {"hook_event_name": "PreToolUse", "session_id": sid, "cwd": str(tmp_path),
            "tool_name": tool, "tool_input": ti}


def _settled(tmp_path, sid, tool, stdout="", **ti):
    return {"hook_event_name": "PostToolUse", "session_id": sid, "cwd": str(tmp_path),
            "tool_name": tool, "tool_input": ti, "tool_response": {"stdout": stdout, "exitCode": 0}}


_H = "#"   # a comment opener, assembled so this file carries no literal directive
# row id -> (history before the act, the act, the guard that discharges it). Every one of these
# moved to the Pre edge 2026-09-25: the act is denied before it runs, and running the guard first
# is the discharge.
_PRE_OBLIGATIONS = {
    "gate.unprobed_fanout": ([], ("Task", {"prompt": "refactor the parser", "description": "x"}),
                             ("Read", {"file_path": "/repo/parser.py"}, "")),
    "gate.relaunched_unchanged": ([("Read", {"file_path": "/repo/p.py"}, ""),
                                   ("Task", {"prompt": "fix it", "description": "x"}, "done")],
                                  ("Task", {"prompt": "fix it", "description": "x"}),
                                  ("Bash", {"command": "pytest -q"}, "1 failed")),
    "gate.unknown_ref_switch": ([], ("Bash", {"command": "git checkout feature"}),
                                ("Bash", {"command": "git branch -a"}, "* main\n  feature")),
    "gate.unobserved_destruction": ([], ("Bash", {"command": "rm -rf build/"}),
                                    ("Bash", {"command": "pytest -q"}, "58 passed")),
    "gate.report_before_run": ([], ("Write", {"file_path": "HANDOFF.md", "content": "The suite passes."}),
                               ("Bash", {"command": "pytest -q"}, "58 passed")),
    "gate.unasked_plan": ([], ("ExitPlanMode", {"plan": "step one, step two"}),
                          ("AskUserQuestion", {"questions": "which target?"}, "main")),
}


@pytest.mark.parametrize("row", sorted(_PRE_OBLIGATIONS))
def test_dispatch_pre_obligation_denies_the_act_until_its_guard_runs(tmp_path, row):
    """Catch: the act, with no guard earlier in the session, is denied and names its row.
    Pass: the same act after the guard settled goes through (that row is silent)."""
    before, (tool, ti), (gtool, gti, gout) = _PRE_OBLIGATIONS[row]
    for sid, guarded in (("catch", False), ("pass", True)):
        (tmp_path / sid).mkdir()
        state_dir = _setup_state(tmp_path / sid)
        for btool, bti, bout in before:
            _run_dispatch(state_dir, _settled(tmp_path, sid, btool, bout, **bti))
        if guarded:
            _run_dispatch(state_dir, _settled(tmp_path, sid, gtool, gout, **gti))
        rc, out = _run_dispatch(state_dir, _pre(tmp_path, sid, tool, **ti))
        if guarded:
            assert row not in out, f"{row} still denies after its guard ran: {out}"
        else:
            decision = json.loads(out)
            assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
            assert row in decision["hookSpecificOutput"]["permissionDecisionReason"]


def test_dispatch_undischarged_waiver_denies_until_an_end_is_named(tmp_path):
    """Catch: a Write introducing a silencing directive with no end is denied. Pass: the same
    directive with a tracked item beside it goes through."""
    state_dir = _setup_state(tmp_path)
    rc, out = _run_dispatch(state_dir, _pre(tmp_path, "w", "Write", file_path="src/x.py",
                                            content=f"x = parse(raw)  {_H} noqa\n"))
    decision = json.loads(out)
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "gate.undischarged_waiver" in decision["hookSpecificOutput"]["permissionDecisionReason"]
    rc, out = _run_dispatch(state_dir, _pre(tmp_path, "w", "Write", file_path="src/x.py",
                                            content=f"x = parse(raw)  {_H} noqa  (until GH-7)\n"))
    assert "gate.undischarged_waiver" not in out


def test_pre_obligation_guard_older_than_the_history_window_still_pays(tmp_path):
    """gate.unprobed_fanout denied a live dispatch whose Reads were more than an hour back: the
    guard was read from `_select_recent`'s 1-hour window. It is read from every row the store
    still holds now (retention, 1.5 h by default, is the remaining named bound)."""
    state_dir = _setup_state(tmp_path)
    _run_dispatch(state_dir, _settled(tmp_path, "old", "Read", "", file_path="/repo/p.py"))
    import sqlite3
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    conn.execute("UPDATE events SET ts = strftime('%Y-%m-%dT%H:%M:%fZ','now','-70 minutes') "
                 "WHERE session_id = 'old'")
    conn.commit(); conn.close()
    rc, out = _run_dispatch(state_dir, _pre(tmp_path, "old", "Task", prompt="go", description="x"))
    assert "gate.unprobed_fanout" not in out


def test_dispatch_unworded_close_gate_blocks_a_close_citing_no_owner_row(tmp_path):
    """gate.unworded_close (opt-in words_file): a close that cites no row of the owner's words
    file blocks; citing `WORDS.tsv:<line>` discharges it."""
    state_dir = _setup_state(tmp_path)
    (tmp_path / "makoto.toml").write_text('words_file = "WORDS.tsv"\n')
    (tmp_path / "WORDS.tsv").write_text("id\twords\nW1\tbuild the index\n")
    stop = {"hook_event_name": "Stop", "session_id": "worded", "cwd": str(tmp_path),
            "last_assistant_message": "Closed: the index is done."}
    rc, out = _run_dispatch(state_dir, stop)
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.unworded_close" in decision["reason"]
    rc, out = _run_dispatch(state_dir, dict(stop, last_assistant_message="Closed WORDS.tsv:2: the index is built."))
    assert "gate.unworded_close" not in (out or "")


def test_dispatch_unrun_count_claim_gate_blocks_a_count_with_no_run(tmp_path):
    """gate.unrun_count_claim: a counted all-pass in the reply with no verifier run blocks."""
    state_dir = _setup_state(tmp_path)
    stop = {"hook_event_name": "Stop", "session_id": "unrun", "cwd": str(tmp_path),
            "last_assistant_message": "All 602 checks pass."}
    rc, out = _run_dispatch(state_dir, stop)
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate.unrun_count_claim: the reply says" in decision["reason"]
