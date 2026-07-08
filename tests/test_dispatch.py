"""end-to-end dispatcher tests for makoto/_dispatch.py (SQLite(WAL) backend)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _setup_state(tmp_path):
    """create a makoto.db with the 3 tables + minimal config; return state_dir."""
    from makoto.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n")
    init_db(state_dir, citations)
    return state_dir


def _run_dispatch(state_dir, payload: dict, extra_env: dict | None = None) -> tuple[int, str]:
    """invoke `python -m makoto._dispatch` with payload on stdin; return (exit, stdout)."""
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    return proc.returncode, proc.stdout.decode("utf-8")


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
    assert rc == 0
    assert out == ""
    assert _dispatch_facts(state_dir) == [], "happy path must write zero dispatch can't-evaluate facts"


def test_dispatch_loose_comparator_emits_block_json(tmp_path):
    """PreToolUse writing a verifier with .startswith( -> block JSON on stdout.

    SPEC-5 Task 8: a PreToolUse block now renders through wire.py's real Pre shape
    (hookSpecificOutput.permissionDecision == "deny"), not the old ad-hoc top-level
    "decision" key -- see makoto/wire.py's _pre_deny.
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
    assert rc == 0  # hook always exits 0; decision is in stdout
    assert out, "expected block JSON on stdout"
    decision = json.loads(out)
    assert decision["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert "content.verifier_predicate_weakened" in reason or "loose" in reason.lower() or "startswith" in reason


def test_dispatch_unparseable_stdin_loud_allows_with_fact(tmp_path):
    """HYBRID: unparseable stdin = a transient/truncated pipe (a real envelope is always valid JSON)
    -> loud-ALLOW (exit 0, empty stdout) AND an on-the-record fact. Never a silent fail-open."""
    state_dir = _setup_state(tmp_path)
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch"],
        input=b"not json{{{",
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    assert proc.returncode == 0
    assert proc.stdout == b""
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
    assert rc == 0
    facts = _dispatch_facts(state_dir)
    assert not any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts


def test_dispatch_clean_appended_chain_self_verify_silent_no_fact(tmp_path, monkeypatch):
    """A real, untampered chain (rows actually appended) must also stay silent -- the self-verify
    is a tamper detector, not a mere-presence trip."""
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    from makoto import ledger as _ledger
    _ledger.append({"kind": "verdict", "key": "a"})
    _ledger.append({"kind": "verdict", "key": "b"})
    payload = {
        "hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    assert rc == 0
    facts = _dispatch_facts(state_dir)
    assert not any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts


def test_dispatch_tampered_chain_self_verify_advisory_fact_never_blocks(tmp_path, monkeypatch):
    """PLANT the fault (hand-edit a chained row's field, leaving its row_hash stale) and SEE it
    fire as an advisory dispatch.chain_tamper fact -- but the session must NOT be blocked (owner
    decision: advisory-first, block-after-soak). Exit code and stdout must be identical to the
    clean-chain case; only the audit trail differs."""
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    from makoto import ledger as _ledger
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
    assert rc == 0
    assert out == ""
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts


def test_dispatch_oversight_clamp_forces_block_under_bypasspermissions(tmp_path):
    """D6: MAKOTO_MODE=loose would normally soften a BLOCK to an ADVISE (allow + additionalContext,
    exit 0) -- but permission_mode=bypassPermissions clamps it back to a real block (exit 2,
    permissionDecision=deny), and the audit row records the clamp + the operator's configured
    (overridden) posture -- never a silent override."""
    import json as _json
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "clamp_test",
        "cwd": "/tmp",
        "permission_mode": "bypassPermissions",
        "tool_input": {"file_path": "/etc/passwd", "content": "x"},
    }
    rc, out = _run_dispatch(state_dir, payload, extra_env={"MAKOTO_MODE": "loose"})
    # A PreToolUse deny is signaled via the JSON body (permissionDecision), not the process exit
    # code -- main() returns 0 for a normal dispatch cycle regardless of outcome; exit 2 is
    # reserved for a tamper-shaped (non-object) payload, a different failure mode entirely.
    assert rc == 0, f"unexpected process exit, got rc={rc} out={out!r}"
    body = _json.loads(out)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny", (
        f"expected a real deny (the clamp), got: {body!r}")

    facts_path = Path(state_dir) / "audit.jsonl"
    rows = [_json.loads(ln) for ln in facts_path.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    clamp = rows[0]["oversight_clamp"]
    assert clamp is not None
    assert clamp["active"] is True
    assert clamp["configured_mode"] == "loose"
    assert clamp["permission_mode"] == "bypassPermissions"


def test_dispatch_no_oversight_clamp_recorded_under_default_permission_mode(tmp_path):
    """The common case: no permission_mode field (or "default") -> oversight_clamp is None on
    the audit row, and MAKOTO_MODE=loose softens normally (advisory, exit 0)."""
    import json as _json
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "no_clamp_test",
        "cwd": "/tmp",
        "tool_input": {"file_path": "/etc/passwd", "content": "x"},
    }
    rc, out = _run_dispatch(state_dir, payload, extra_env={"MAKOTO_MODE": "loose"})
    assert rc == 0, f"expected a softened advisory (exit 0), got rc={rc} out={out!r}"
    body = _json.loads(out)
    assert "additionalContext" in body["hookSpecificOutput"]

    facts_path = Path(state_dir) / "audit.jsonl"
    rows = [_json.loads(ln) for ln in facts_path.read_text().splitlines() if ln.strip()]
    assert rows[0]["oversight_clamp"] is None


def test_dispatch_non_object_payload_blocks_exit_2_with_fact(tmp_path):
    """HYBRID: valid JSON that is NOT an object is tamper-shaped — a truncated pipe yields INVALID
    json, and Claude Code's envelope is always an object, so a parseable non-object is anomalous ->
    fail CLOSED (exit 2 + stderr reason + fact). Tested for a list, a string, and `null`."""
    state_dir = _setup_state(tmp_path)
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    for raw in (b'["not","an","object"]', b'"a bare string"', b'null'):
        proc = subprocess.run(
            [sys.executable, "-m", "makoto._dispatch"],
            input=raw, capture_output=True, env=env,
            cwd=str(Path(__file__).parent.parent),
        )
        assert proc.returncode == 2, (raw, proc.returncode, proc.stderr)
        assert b"object" in proc.stderr.lower(), (raw, proc.stderr)
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.non_object_payload" for f in facts), facts


def test_dispatch_db_init_failure_loud_allows_with_fact(tmp_path, monkeypatch):
    """HYBRID infra: lazy DB init failure -> loud-ALLOW (exit 0) + fact (never crash, never silent)."""
    import io
    from makoto import _dispatch
    state_dir = tmp_path / "makoto_state"
    state_dir.mkdir(parents=True)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    monkeypatch.setattr(_dispatch, "_ensure_db_initialized", lambda *a, **k: False)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/tmp", "tool_input": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert _dispatch.main() == 0
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.db_init_failed" for f in facts), facts


def test_dispatch_db_lock_loud_allows_with_fact(tmp_path, monkeypatch):
    """HYBRID infra: write-lock not acquired -> loud-ALLOW (exit 0) + fact."""
    import io
    from makoto import _dispatch
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    monkeypatch.setattr(_dispatch, "_connect_with_retry", lambda *a, **k: None)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/tmp", "tool_input": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert _dispatch.main() == 0
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.db_locked" for f in facts), facts


def test_dispatch_body_exception_loud_allows_with_fact(tmp_path, monkeypatch):
    """HYBRID infra: an unexpected body fault -> loud-ALLOW (exit 0, never crash to non-zero) + fact
    (Exception, not BaseException, so Ctrl-C still propagates)."""
    import io
    from makoto import _dispatch
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    def boom(*a, **k):
        raise RuntimeError("ingest blew up")
    monkeypatch.setattr(_dispatch, "_ingest_event", boom)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/tmp", "tool_input": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert _dispatch.main() == 0
    facts = _dispatch_facts(state_dir)
    assert any(f.get("pattern_id") == "dispatch.exception" for f in facts), facts


def test_dispatch_lazy_init_creates_db_when_absent(tmp_path):
    """if makoto.db is absent, _dispatch.main() creates it on first call."""
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
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    assert proc.returncode == 0
    db_file = state_dir / "makoto.db"
    assert db_file.is_file(), "lazy init should have created makoto.db"


def test_connect_with_retry_fails_open_on_lock(monkeypatch):
    """A write lock held past the busy_timeout budget must fail OPEN: _connect_with_retry
    returns None so the caller skips evaluation and the agent's tool call proceeds.

    SQLite(WAL) makes lock contention rare (concurrent readers + busy_timeout absorb
    most of it), but the fail-open path is safety-critical — a hung lock must never
    crash or block the hook. Tested at the unit level so it is fast and deterministic
    rather than racing two processes for a lock.
    """
    import sqlite3
    from makoto import _dispatch
    calls = {"n": 0}

    def _locked(*a, **kw):
        calls["n"] += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", _locked)
    assert _dispatch._connect_with_retry(Path("/tmp/whatever.db")) is None
    assert calls["n"] == _dispatch._LOCK_RETRY_ATTEMPTS  # retried the full budget, then gave up


def test_connect_with_retry_reraises_non_lock_errors(monkeypatch):
    """A non-lock OperationalError is a real bug, not contention — it must propagate,
    never be silently swallowed as fail-open (that would mask corruption)."""
    import sqlite3
    from makoto import _dispatch

    def _boom(*a, **kw):
        raise sqlite3.OperationalError("no such table: events")

    monkeypatch.setattr(sqlite3, "connect", _boom)
    with pytest.raises(sqlite3.OperationalError):
        _dispatch._connect_with_retry(Path("/tmp/whatever.db"))


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
    assert rc == 0
    assert out == ""
    post_size = audit_path.stat().st_size if audit_path.exists() else 0
    assert post_size == pre_size, (
        f"empty-findings hook must not write an audit row; size grew {pre_size}->{post_size}"
    )


def test_dispatch_still_writes_audit_row_when_finding_fires(tmp_path):
    """only-fires policy must NOT silence real fires — pattern 1.1 still records its row."""
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
    assert rc == 0
    # SPEC-5 Task 8: a PreToolUse block renders wire.py's real Pre shape (deny), not a literal
    # "block" substring -- see test_dispatch_loose_comparator_emits_block_json for the full shape.
    assert '"deny"' in out, f"pattern 1.1 should still emit a deny decision; got {out!r}"
    assert audit_path.exists()
    post_size = audit_path.stat().st_size
    assert post_size > pre_size, "fire-row must be recorded"


def test_dispatch_env_disable_silences_specific_pattern(tmp_path):
    """MAKOTO_DISABLE_PATTERNS=1.1 makes pattern 1.1 a no-op for this dispatcher call.

    The same payload that fires 1.1 under normal config must produce no block JSON
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
    assert rc == 0
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
    assert rc == 0
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0].get("tool_name") == "Write", (
        f"expected tool_name='Write' on fire row; got {rows[0].get('tool_name')!r}"
    )
    assert rows[0]["pattern_fires"] == ["content.verifier_predicate_weakened"]


def test_dispatch_posttooluse_write_records_ledger_touch(tmp_path):
    """PostToolUse Write -> a `touched` ledger row (the update recorder, wired live)."""
    import sqlite3
    from makoto import ledger
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
    assert rc == 0
    assert out == "", "PostToolUse must never emit a decision"
    conn = sqlite3.connect(str(state_dir / "makoto.db"))
    try:
        row = ledger.read_key(conn, "src/auth.py")
    finally:
        conn.close()
    assert row is not None and row["kind"] == "touched", f"expected touched row; got {row!r}"


def test_dispatch_posttooluse_bash_records_ledger_value(tmp_path):
    """PostToolUse Bash -> a `value` ledger row keyed by the path token in the command."""
    import sqlite3
    from makoto import ledger
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
    assert rc == 0
    conn = sqlite3.connect(str(state_dir / "makoto.db"))
    try:
        row = ledger.read_key(conn, "tests/auth_test.py")
    finally:
        conn.close()
    assert row is not None and row["kind"] == "value", f"expected value row; got {row!r}"
    assert "120 tests/auth_test.py" in (row["value"] or "")


def test_dispatch_test_delta_redirect_advises_on_newly_failing_test(tmp_path):
    """Task 3's test-delta redirect: a test run whose verdict set changed vs the PRIOR recorded
    run emits an ADVISE-tier additionalContext on the CORRECT (Post) edge -- never blocks, never
    denies the call, and never claims a PreToolUse-shaped hookEventName for a PostToolUse event
    (the _HOOK_TO_EDGE gap this task also found and fixed)."""
    import json as _json
    state_dir = _setup_state(tmp_path)
    sid = "delta_s1"
    first = {
        "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid, "cwd": "/tmp",
        "tool_input": {"command": "pytest -q"},
        "tool_response": {"stdout": "PASSED tests/x.py::test_a\n", "stderr": "", "exitCode": 0},
    }
    rc1, out1 = _run_dispatch(state_dir, first)
    assert rc1 == 0
    assert out1 == "", "no PRIOR run to diff against yet -> nothing to say"

    second = {
        "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid, "cwd": "/tmp",
        "tool_input": {"command": "pytest -q"},
        "tool_response": {"stdout": "FAILED tests/x.py::test_a\n", "stderr": "", "exitCode": 1},
    }
    rc2, out2 = _run_dispatch(state_dir, second)
    assert rc2 == 0
    body = _json.loads(out2)
    assert body["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "newly failing: test_a" in body["hookSpecificOutput"]["additionalContext"]

    # Found while building the D9 demo corpus: the delta redirect fired on the wire but was
    # invisible to the audit trail/chain until this fix -- must now leave a real record.
    from makoto import audit as _audit_mod, ledger as _ledger_mod
    audit_lines = list(_audit_mod.read_rows(state_dir))
    assert any(r.get("pattern_fires") == ["makoto.test_delta"] for r in audit_lines), audit_lines
    chain_rows = _ledger_mod.read(root=state_dir)
    assert any(r.get("kind") == "audit" and r.get("pattern_fires") == ["makoto.test_delta"]
              for r in chain_rows), chain_rows


def test_dispatch_test_delta_redirect_silent_when_verdict_set_is_unchanged(tmp_path):
    state_dir = _setup_state(tmp_path)
    sid = "delta_s2"
    payload = {
        "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid, "cwd": "/tmp",
        "tool_input": {"command": "pytest -q"},
        "tool_response": {"stdout": "FAILED tests/x.py::test_a\n", "stderr": "", "exitCode": 1},
    }
    rc1, _ = _run_dispatch(state_dir, payload)
    assert rc1 == 0
    rc2, out2 = _run_dispatch(state_dir, payload)   # same verdict set, re-run
    assert rc2 == 0
    assert out2 == ""


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
    assert rc == 0
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
    assert rc == 0
    stop = {"hook_event_name": "Stop", "session_id": "gc", "cwd": str(tmp_path),
            "last_assistant_message": "Done — all tests pass now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "green_claim gate must block on a green claim over a recorded red run"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "test" in decision["reason"].lower()


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
    assert rc == 0
    assert out == "", "run was green -> green_claim gate must stay silent"


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
    assert rc == 0
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
    assert rc == 0
    assert out == "", "a referenced (not produced) path must not false-block"


def test_dispatch_advance_gate_blocks_by_default(tmp_path):
    """2026-06-01 flip: the advance gate BLOCKS live by default — no env var needed. Record an
    open commitment (Stop 1), then claim UNIVERSAL completion while it is undischarged (Stop 2):
    the advance gate fires AND blocks. Validated FP-clean (0 fires across 1335 corpus sessions
    after the proposal-menu / code-fence sourcing guards); the reason-bound retraction path
    (next test) clears legitimately-dropped promises so honest re-prioritization never blocks."""
    state_dir = _setup_state(tmp_path)
    promise = {
        "hook_event_name": "Stop", "session_id": "adv", "cwd": str(tmp_path),
        "last_assistant_message": "Next I will add rate limiting to src/promised_zzz.py.",
    }
    advance = {
        "hook_event_name": "Stop", "session_id": "adv", "cwd": str(tmp_path),
        "last_assistant_message": "Everything is done — all complete.",
    }
    _run_dispatch(state_dir, promise)
    rc, out = _run_dispatch(state_dir, advance)   # universal-completion claim + undischarged commitment
    assert rc == 0
    assert out, "advance gate must block by default after the flip"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "src/promised_zzz.py" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.advance" in r.get("pattern_fires", []) for r in rows), \
        "the advance fire must still be audited"


def test_dispatch_advance_gate_shadow_when_disabled(tmp_path):
    """MAKOTO_DISABLE_GATES=1 returns the advance gate to shadow: still audited, no block —
    the single escape valve, shared with the completion gate."""
    state_dir = _setup_state(tmp_path)
    promise = {
        "hook_event_name": "Stop", "session_id": "adv_off", "cwd": str(tmp_path),
        "last_assistant_message": "Next I will add rate limiting to src/promised_zzz.py.",
    }
    advance = {
        "hook_event_name": "Stop", "session_id": "adv_off", "cwd": str(tmp_path),
        "last_assistant_message": "Everything is done — all complete.",
    }
    _run_dispatch(state_dir, promise, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    rc, out = _run_dispatch(state_dir, advance, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    assert rc == 0
    assert out == "", "disabled advance gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.advance" in r.get("pattern_fires", []) for r in rows), \
        "the shadow advance fire must still be audited so its FP rate can be mined"


def test_dispatch_dropped_gate_blocks_by_default(tmp_path):
    """Behavioral blocking pin for gate.dropped THROUGH the real dispatch — the falsifiability gap
    its 3 sibling gates each closed but it landed without. A forward promise carrying identifying
    info (a named symbol), left undischarged at turn-end (file absent, no Write recorded), BLOCKS
    live by default. Breaking the _blocking_gate_ids() filter reddens THIS (not just the structural
    set-equality test), proving gate.dropped actually stops the agent, not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "drop_default",
        "cwd": str(tmp_path),  # src/gates_zzz.py does not exist here -> undischarged
        "last_assistant_message": "I'll add def validate_seal_zzz to src/gates_zzz.py next.",
    }
    rc, out = _run_dispatch(state_dir, payload)   # no env -> dropped gate blocks live
    assert rc == 0
    assert out, "dropped gate must block by default on an undischarged forward promise"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "validate_seal_zzz" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.dropped" in r.get("pattern_fires", []) for r in rows), \
        "the dropped fire must still be audited"


def test_dispatch_contract_order_gate_blocks_on_open_remainder(tmp_path):
    """Behavioral blocking pin for gate.contract_order's Stop remainder guard (SPEC-5), driven
    through the real dispatch end-to-end: a SessionStart admits a declared plan from the on-disk
    artifact, then a Stop with the plan still unfinished BLOCKS live by default."""
    state_dir = _setup_state(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "makoto-plan.jsonl").write_text(
        '{"what":"Write","passthrough":"auth.py","where":"auth.py","id":"n1"}\n'
    )
    session = "contract_order_default"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "contract_order gate must block by default on an unfinished plan"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "n1" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.contract_order" in r.get("pattern_fires", []) for r in rows), \
        "the contract_order fire must still be audited"


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
    assert rc == 0
    assert out == "", "a discharged promise (symbol present on disk) must not block"


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
    assert rc == 0
    assert out == "", "disabled dropped gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.dropped" in r.get("pattern_fires", []) for r in rows), \
        "the shadow dropped fire must still be audited so its FP rate can be mined"


def test_dispatch_liveness_gate_blocks_on_illusory_code(tmp_path):
    """Behavioral blocking pin for the liveness gate THROUGH the real dispatch. A .py file
    touched this turn (recorded via a PostToolUse Write -> ledger touched-key) and present on disk
    with a dead pure statement (a value computed and never reaching I/O) BLOCKS at Stop by default.
    Breaking the _blocking_gate_ids() filter reddens THIS, proving the gate actually stops the
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
    assert rc == 0
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
    assert rc == 0
    assert out == "", "a material statement (its value reaches the return) must not block"


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
    assert rc == 0
    assert out == "", "disabled liveness gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.liveness" in r.get("pattern_fires", []) for r in rows), \
        "the shadow liveness fire must still be audited so its FP rate can be mined"


def test_dispatch_hollow_test_gate_blocks_on_hollow_test(tmp_path):
    """Behavioral blocking pin for gate.hollow_test THROUGH the real dispatch. A test file touched
    this turn (recorded via a PostToolUse Write -> ledger touched-key) and present on disk with a
    HOLLOWED test (no assertion of any kind) BLOCKS at Stop by default. Breaking the
    _blocking_gate_ids() filter reddens THIS, proving the gate actually stops the agent end-to-end,
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
    assert rc == 0
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
    assert rc == 0
    assert out == "", "a test with a real assertion must not block"


def test_dispatch_canon_gate_blocks_by_default(tmp_path):
    """Behavioral blocking pin for gate.canon THROUGH the real dispatch. A Bash call recorded at
    PostToolUse with tool_response={"interrupted": true} and nothing after it -> the turn's LAST
    call is in a direct error state -> canon.timeout fires and BLOCKS at Stop by default. Breaking
    the _blocking_gate_ids() filter reddens THIS, proving the gate actually stops the agent
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
    assert rc == 0
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
    assert rc == 0
    assert out, "gate.canon_fingerprints must block by default on a robust-core fingerprint fire"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "canon.nosrc_destruct" in decision["reason"]


def test_dispatch_canon_fingerprints_advisory_gate_never_blocks_even_when_it_fires(tmp_path):
    """Behavioral pin mirroring test_dispatch_self_wired_gate_never_blocks_even_when_it_fires:
    gate.canon_fingerprints_advisory fires (audited) but NEVER blocks, even when its own fingerprint
    condition holds -- an Edit on a test file that degenerates a real assertion into a tautology,
    with no green test run recorded (nogreen_weakened)."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "session_id": "canon_fp_advise",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": "tests/test_x.py",
                           "old_string": "assert x == 5", "new_string": "assert True"},
            "tool_response": {}}
    rc, out = _run_dispatch(state_dir, post)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": "canon_fp_advise", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", "gate.canon_fingerprints_advisory must NEVER block, even when it fires"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.canon_fingerprints_advisory" in r.get("pattern_fires", []) for r in rows), \
        "the advisory fire must still be audited so it leaves a forensic trail"


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
    assert rc == 0
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
    assert rc == 0
    assert out == "", "disabled canon gate must not block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.canon" in r.get("pattern_fires", []) for r in rows), \
        "the shadow canon fire must still be audited so its FP rate can be mined"


def test_dispatch_reason_bound_retraction_clears_so_advance_does_not_fire(tmp_path):
    """The reconcile wiring end-to-end: promise (Stop 1), then RETRACT it with a surfaced
    reason (Stop 2), then claim universal completion (Stop 3). The commitment is cleared
    (status='retracted'), so the advance gate does NOT fire even in the audit log — the
    legitimately-dropped promise is not held against the AI. Contrast with the test above,
    where the SAME promise + universal-completion (no retraction) DOES fire advance."""
    state_dir = _setup_state(tmp_path)
    sid = "adv_retract"
    promise = {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
               "last_assistant_message": "Next I will add rate limiting to src/promised_zzz.py."}
    retract = {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
               "last_assistant_message": "Skipping src/promised_zzz.py for this sprint per your note."}
    advance = {"hook_event_name": "Stop", "session_id": sid, "cwd": str(tmp_path),
               "last_assistant_message": "Everything is done — all complete."}
    _run_dispatch(state_dir, promise)
    _run_dispatch(state_dir, retract)
    rc, out = _run_dispatch(state_dir, advance)
    assert rc == 0 and out == ""
    # only-fires audit policy: a missing audit.jsonl means ZERO patterns fired across all three
    # Stop dispatches — which already proves advance did not fire. A regression that fired advance
    # would recreate the file with a gate.advance row, flipping the any(...) below to True.
    audit_path = state_dir / "audit.jsonl"
    rows = ([json.loads(l) for l in audit_path.read_text().splitlines() if l.strip()]
            if audit_path.exists() else [])
    assert not any("gate.advance" in r.get("pattern_fires", []) for r in rows), \
        "a reason-bound retraction must clear the commitment so advance never fires on it"


def test_dispatch_fabricated_action_gate_blocks(tmp_path):
    """Behavioral blocking pin for gate.fabricated_action THROUGH the real dispatch. A Stop message
    claims a completed tool action with a distinctive (backticked) object whose command NO recorded
    tool event this session ran -> the gate walks ctx.history (the events-table slice, empty of any
    matching command here) -> BLOCKS live by default. Breaking _blocking_gate_ids() or the history wiring
    reddens THIS, proving the fabricated-action claim actually stops the agent end-to-end."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "fab_action",
        "cwd": str(tmp_path),
        "last_assistant_message": "I ran `pytest tests/zzz_unrun.py -q` and it all passed.",
    }
    rc, out = _run_dispatch(state_dir, payload)   # no prior command recorded -> fabricated -> blocks
    assert rc == 0
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
    assert rc == 0
    assert out == "", "a tool call this turn discharges the action claim -> must not block"


def test_dispatch_named_test_gate_blocks_after_recorded_named_red(tmp_path):
    """Behavioral blocking pin for gate.named_test THROUGH the real dispatch. A failing PER-TEST run
    (FAILED ...::test_foo) recorded at PostToolUse, then a claim that test_foo passes at Stop -> the
    gate reads the per-name verdict from ctx.history -> BLOCKS live. Breaking _blocking_gate_ids() or the
    history wiring reddens THIS, proving the named-test claim stops the agent end-to-end."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "nt",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "FAILED tests/x.py::test_foo - AssertionError\n1 failed in 0.1s",
                              "stderr": "", "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)              # records the per-test red into history
    assert rc == 0
    stop = {"hook_event_name": "Stop", "session_id": "nt", "cwd": str(tmp_path),
            "last_assistant_message": "Good news — test_foo passes now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "named_test gate must block a named-test pass-claim over that test's recorded red"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "test_foo" in decision["reason"]


def test_dispatch_named_test_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop falsifier: the same fabricated named-test pass-claim that blocks through Stop
    (test_dispatch_named_test_gate_blocks_after_recorded_named_red above) must block IDENTICALLY
    when it arrives as a SubagentStop event — a sub-agent's own completion claim is checked by the
    same gates a main-thread Stop claim is checked by. Breaking the `hook_event in ("Stop",
    "SubagentStop")` branch in _dispatch.main() reddens this while leaving the Stop-path sibling
    test green, proving the SubagentStop route specifically."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "nt_sub",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "FAILED tests/x.py::test_foo - AssertionError\n1 failed in 0.1s",
                              "stderr": "", "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)              # records the per-test red into history
    assert rc == 0
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "nt_sub", "cwd": str(tmp_path),
                      "last_assistant_message": "Good news — test_foo passes now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert rc == 0
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
    assert rc == 0
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
    assert rc == 0
    assert out, "completion gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "src/nonexistent_zzz.py" in decision["reason"]


def test_dispatch_advance_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_advance_gate_blocks_by_default."""
    state_dir = _setup_state(tmp_path)
    promise = {
        "hook_event_name": "SubagentStop", "session_id": "adv_sub", "cwd": str(tmp_path),
        "last_assistant_message": "Next I will add rate limiting to src/promised_zzz.py.",
    }
    advance = {
        "hook_event_name": "SubagentStop", "session_id": "adv_sub", "cwd": str(tmp_path),
        "last_assistant_message": "Everything is done — all complete.",
    }
    _run_dispatch(state_dir, promise)
    rc, out = _run_dispatch(state_dir, advance)
    assert rc == 0
    assert out, "advance gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "src/promised_zzz.py" in decision["reason"]


def test_dispatch_green_claim_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_green_claim_gate_blocks_after_recorded_red_run."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "gc_sub",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "=== 2 failed, 9 passed in 3.0s ===", "stderr": "",
                              "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)
    assert rc == 0
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "gc_sub", "cwd": str(tmp_path),
                      "last_assistant_message": "Done — all tests pass now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert rc == 0
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
    assert rc == 0
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
    assert rc == 0
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
    assert rc == 0
    assert out, "hollow_test gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "hollow" in decision["reason"]


def test_dispatch_canon_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_canon_gate_blocks_by_default."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "canon_block_sub",
            "cwd": str(tmp_path),
            "tool_input": {"command": "some-long-running-thing"},
            "tool_response": {"interrupted": True}}
    rc, out = _run_dispatch(state_dir, post)
    assert rc == 0 and out == ""
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "canon_block_sub",
                      "cwd": str(tmp_path), "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert rc == 0
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
    assert rc == 0
    assert out, "stale_pass gate must block through SubagentStop just as it does through Stop"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "tests/t.py::test_red" in decision["reason"]


def test_dispatch_self_wired_gate_never_blocks_through_subagent_stop(tmp_path):
    """SubagentStop mirror of test_dispatch_self_wired_gate_never_blocks_even_when_it_fires: the
    advisory-only exception (FABLE DECISION, 2026-07-05) must never block through SubagentStop
    either — fires (audited) but never turns into a block decision, matching the Stop-event pin."""
    state_dir = _setup_state(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto._dispatch"}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto._dispatch"}]}],
        # Stop entry deliberately absent -> a partial strip -> gate.self_wired fires, advisory only.
    }}))
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "sw_sub", "cwd": str(tmp_path),
                      "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, subagent_stop)
    assert rc == 0
    assert out == "", "gate.self_wired must NEVER block through SubagentStop, even when it fires"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.self_wired" in r.get("pattern_fires", []) for r in rows), \
        "the advisory self_wired fire must still be audited through SubagentStop too"


def test_dispatch_stale_pass_gate_blocks_on_live_lastfailed(tmp_path):
    """Behavioral blocking pin for gate.stale_pass THROUGH the real dispatch. pytest's own
    lastfailed under the Stop payload's cwd names a failing node whose test STILL EXISTS, and the
    final message makes a clean whole-suite pass-claim -> the gate reads the on-disk record via
    ctx.cwd -> BLOCKS live. Breaking _blocking_gate_ids() or the cwd wiring reddens THIS."""
    state_dir = _setup_state(tmp_path)
    cache = tmp_path / ".pytest_cache" / "v" / "cache"
    cache.mkdir(parents=True)
    (cache / "lastfailed").write_text(json.dumps({"tests/t.py::test_red": True}))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("def test_red():\n    assert False\n")
    stop = {"hook_event_name": "Stop", "session_id": "sp", "cwd": str(tmp_path),
            "last_assistant_message": "Done — all tests pass."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "stale_pass gate must block a whole-suite pass-claim over a live lastfailed record"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "tests/t.py::test_red" in decision["reason"]


def test_dispatch_self_wired_gate_never_blocks_even_when_it_fires(tmp_path):
    """Behavioral pin for gate.self_wired's ONE deliberate exception to discovered<=>live<=>blocking
    (2026-07-05, FABLE DECISION): it IS discovered (present in _blocking_gate_ids() like every other
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
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto._dispatch"}]}],
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto._dispatch"}]}],
        # Stop entry deliberately absent -> a partial strip -> gate.self_wired fires, advisory only.
    }}))
    stop = {"hook_event_name": "Stop", "session_id": "sw", "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", "gate.self_wired must NEVER block, even when its predicate fires"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.self_wired" in r.get("pattern_fires", []) for r in rows), \
        "the advisory self_wired fire must still be audited so a partial strip leaves a forensic trail"


def test_no_shadow_gate_every_gate_blocks():
    """Warning-tier-elimination invariant. SPEC-C item 2 (FABLE DECISION, 2026-07-07) restated
    this STRUCTURALLY: blocking-eligibility now derives from each check's own declared `.posture`
    (`_blocking_gate_ids()`, checks._loader-backed), not from mere presence in load_stopchecks()'s
    GATE discovery. Before this change "discovered" and "blocking-eligible" were forced equal by
    construction, requiring a separate hand-maintained `_ADVISORY_ALLOWLIST`
    (test_stop_gate_level_invariant.py) to excuse the 2 ids that are discovered but can never
    actually block. Now those 2 ids are simply never IN the blocking set at all — no allowlist
    needed, and "blocking-eligible" means precisely what it says.

    Per FABLE's explicit condition on this migration: the expected BLOCK-id set below is a
    LITERAL, hand-written set, not re-derived from the same `.posture` field `_blocking_gate_ids()`
    itself reads — deriving the expectation from the thing under test would be a bypassable
    tautology (a broken posture value would break the code and its own "check" identically,
    passing vacuously). A future shadow gate (discoverable but routed around _blocking_gate_ids(),
    or wired into run_stop_checks without a `.posture` at all) turns THIS red because it will not
    appear in an independently-declared literal."""
    from makoto.stopchecks import load_stopchecks
    from makoto._dispatch import _blocking_gate_ids
    discovered = {g.id for g in load_stopchecks()}
    assert discovered == {"gate.completion", "gate.advance", "gate.green_claim", "gate.dropped",
                          "gate.fabricated_action", "gate.named_test", "gate.stale_pass",
                          "gate.liveness",     # liveness folded in from the collapsed close-check tier
                          "gate.hollow_test",  # HOLLOWED-class detector (SPIRIT.md §4), same split as liveness
                          "gate.canon",        # ported agnostic Stop primitives canon.timeout/canon.recur
                          "gate.canon_fingerprints",            # SPEC-5 Task 9: BLOCK-tier canon fingerprints
                          "gate.canon_fingerprints_advisory",    # SPEC-5 Task 9: ADVISE-tier sibling
                          "gate.contract_order",     # SPEC-5 (Makoto absorbs Assay): the plan's Stop
                                                      # remainder guard; renamed from makoto.contract_order
                                                      # (SPEC-C item 3, one namespace)
                          "gate.self_wired"}   # GATE-discovered, but posture=ADVISE -> excluded below
    # BLOCKING-eligible is now a strict SUBSET of discovered: exactly the 12 posture=BLOCK ids,
    # pinned as an independent literal (see docstring -- must not be re-derived from .posture).
    assert set(_blocking_gate_ids()) == {
        "gate.completion", "gate.advance", "gate.green_claim", "gate.dropped",
        "gate.fabricated_action", "gate.named_test", "gate.stale_pass", "gate.liveness",
        "gate.hollow_test", "gate.canon", "gate.canon_fingerprints", "gate.contract_order",
    }
    # The 2 GATE-discovered advisory ids are discovered but deliberately NOT blocking-eligible.
    assert discovered - set(_blocking_gate_ids()) == {"gate.self_wired", "gate.canon_fingerprints_advisory"}
    # The check.quantity / claim_check capability no longer EXISTS: no discovered gate is named it,
    # and the package exposes no such callable (re-adding it as a gate turns this red).
    assert "claim_check" not in {g.fn.__name__ for g in load_stopchecks()}
    assert "dropped_gate" in {g.fn.__name__ for g in load_stopchecks()}       # live -> discovered + blocking


def test_every_blocking_gate_has_a_behavioral_dispatch_block_test():
    """Gap-CLASS closer (generalizes the gate.dropped miss). The set-equality pin above is STRUCTURAL:
    dropping a gate from _blocking_gate_ids() reddens it, but so would a legitimate addition — it pins
    the set's value, not the gate's blocking BEHAVIOR. The behavioral pin is a dispatch test that
    drives a triggering Stop message all the way through `_run_dispatch` and asserts decision==block;
    only THAT reddens when the blocking-filter LOGIC regresses (verified: breaking the
    _blocking_gate_ids() filter reddens these 4 behavioral tests, not the structural ones).
    gate.dropped shipped without one — so
    require every blocking gate to carry a `test_dispatch_<gate>_gate_blocks*` test, by the same naming
    convention its 3 siblings already follow. A future blocking gate added without one reddens HERE,
    at landing, instead of leaving its real blocking behavior unfalsifiable.

    gate.self_wired (2026-07-05, FABLE DECISION) is the one documented exception: it IS discovered
    (and so appears in _blocking_gate_ids() by the discovered<=>live<=>blocking wiring), but it
    ships at level="advisory", never "error" — it structurally CANNOT cause a block decision, so a
    "...gate_blocks" test for it would assert something false. Its behavioral pin instead lives in
    test_dispatch_self_wired_gate_never_blocks_even_when_it_fires (this file), which proves the
    opposite claim: it fires (audited) and never blocks."""
    from pathlib import Path as _P
    from makoto._dispatch import _blocking_gate_ids
    # gate.canon_fingerprints_advisory (SPEC-5 Task 9, FABLE DECISION 26) is the second documented
    # exception, same shape as gate.self_wired: discovered (so it appears in _blocking_gate_ids())
    # but ships at level="advisory" only, never "error" -- structurally cannot block. Its behavioral
    # pin is test_dispatch_canon_fingerprints_advisory_gate_never_blocks_even_when_it_fires below.
    _ADVISORY_EXEMPT = {"gate.self_wired", "gate.canon_fingerprints_advisory"}
    src = _P(__file__).read_text()
    missing = [gid for gid in _blocking_gate_ids()
               if gid not in _ADVISORY_EXEMPT
               and f"def test_dispatch_{gid.split('.')[-1]}_gate_blocks" not in src]
    assert not missing, (f"blocking gate(s) without a BEHAVIORAL dispatch-block test (a structural "
                         f"set-membership pin is not enough — see this test's docstring): {missing}")


# ---------------------------------------------------------------------------
# Line-level pinning tests (mutation-audit gap closure for _dispatch.py).
# Each test below reddens a specific surviving single-token mutant; the
# (lineno, kind) it closes is named in the docstring.
# ---------------------------------------------------------------------------


def test_dispatch_lazy_init_success_propagates_so_firing_event_blocks(tmp_path):
    """Pins line 62 (`_ensure_db_initialized` success -> `return True`), RETURN and CONST.

    On the lazy-init path (db absent), a successful init MUST return truthy so main()
    does NOT fail open at line 250. A firing PreToolUse event (pattern 1.1, loose
    comparator in a verifier file) created via lazy init must still emit block JSON.
    If `return True` is mutated to `return None`/`return False`, main() fails open and
    stdout is empty -> this assertion reddens.
    """
    state_dir = tmp_path / "makoto_state"
    state_dir.mkdir(parents=True)  # dir exists, but NO makoto.db -> dispatcher inits lazily
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
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    assert proc.returncode == 0
    out = proc.stdout.decode("utf-8")
    assert (state_dir / "makoto.db").is_file(), "lazy init should have created makoto.db"
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
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    assert proc.returncode == 0, (
        "lazy-init failure must fail OPEN (exit 0), never crash the hook; "
        f"got rc={proc.returncode}, stderr={proc.stderr.decode('utf-8')!r}"
    )
    assert proc.stdout == b"", "a failed-open dispatch must emit no decision"


def test_connect_with_retry_sleeps_backoff_between_attempts(monkeypatch):
    """Pins line 89 (`if attempt < _LOCK_RETRY_ATTEMPTS - 1:` guarding the backoff sleep), NOT and CMP.

    Under sustained lock contention, the dispatcher backs off between every attempt EXCEPT the
    last -> exactly (_LOCK_RETRY_ATTEMPTS - 1) sleeps. Negating the test (NOT) sleeps only on the
    last attempt (1 sleep); swapping the comparator `<`->`>` (CMP) never sleeps (0 sleeps). Either
    mutation changes the observed sleep count, so pinning it to ATTEMPTS-1 reddens both.
    """
    import sqlite3
    from makoto import _dispatch
    sleeps = {"n": 0}

    def _locked(*a, **kw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", _locked)
    monkeypatch.setattr(_dispatch.time, "sleep", lambda _s: sleeps.__setitem__("n", sleeps["n"] + 1))
    assert _dispatch._connect_with_retry(Path("/tmp/whatever.db")) is None
    assert sleeps["n"] == _dispatch._LOCK_RETRY_ATTEMPTS - 1, (
        "backoff must sleep between every attempt except the last "
        f"(expected {_dispatch._LOCK_RETRY_ATTEMPTS - 1}, got {sleeps['n']})"
    )


def test_keyword_hit_empty_keywords_returns_false():
    """Pins line 122 (`if not pattern.keywords: return False`), RETURN and CONST.

    A pattern with no keywords matches nothing — the guard must return False. Mutating
    `return False` to `return None`/`return True` makes an empty-keyword pattern (synthetic,
    a defensive branch) claim a hit on any payload. Direct unit on the helper.
    """
    from makoto._dispatch import _keyword_hit
    from makoto.schema import PreCheck
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
    from makoto._dispatch import _keyword_hit
    from makoto.schema import PreCheck
    pattern = PreCheck(id="y", description="d", fire_level="error",
                      predicate_module="m", keywords=["foo", "bar"], retry_hint="")
    assert _keyword_hit(pattern, "xx foo yy bar zz") is True


def test_dispatch_select_recent_returns_history_so_history_predicate_fires(tmp_path):
    """Pins line 110 (`_select_recent` -> `return conn.execute(...).fetchall()`), RETURN.

    A history-walking predicate (1.22: fabricated commit SHA) needs the real prior-event slice.
    A Stop claiming a commit SHA with no prior `git commit` tool_use fires 1.22 and blocks.
    If `_select_recent` returns None instead of the list, `for entry in history` raises TypeError
    inside the predicate, which dispatch swallows -> 1.22 never fires -> no block JSON. Asserting
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
    assert rc == 0
    assert out, "1.22 (fabricated SHA) must fire on a real history slice -> block JSON"
    assert json.loads(out)["decision"] == "block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("content.fabricated_commit_sha" in r.get("pattern_fires", []) for r in rows), \
        "the 1.22 fire must be recorded (history slice was actually returned)"


def test_dispatch_decision_carries_retry_hint_when_finding_has_one(tmp_path):
    """PreCheck 1.1 produces a truthy retry_hint (via `_jit_hint`). SPEC-5 Task 8: the live
    decision JSON no longer has a separate top-level "retry_hint" key -- `_emit_decision` folds
    the JIT hint (the pattern's own retry_hint text + the makoto-allow hatch + the conventions
    pointer) into the finding's message as the wire Decision's `.detail`, which wire.py's
    `_pre_deny` surfaces as `permissionDecisionReason`. Asserting the hint text is present there
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
    assert rc == 0
    assert out, "pattern 1.1 must emit a block decision"
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

    PreCheck 1.1 is an error-level finding, so the recorded audit row's exit_code must be 2.
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
    assert rc == 0
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert rows, "the error-level fire must record an audit row"
    fire_rows = [r for r in rows if "content.verifier_predicate_weakened" in r.get("pattern_fires", [])]
    assert fire_rows, "expected a 1.1 fire row"
    assert fire_rows[0].get("exit_code") == 2, (
        "an error-level finding must record exit_code=2 in the audit row; "
        f"got {fire_rows[0].get('exit_code')!r}"
    )
