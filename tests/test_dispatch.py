"""end-to-end dispatcher tests for makoto/_dispatch.py (SQLite(WAL) backend)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _setup_state(tmp_path):
    """create a makoto.record.db with the 3 tables + minimal config; return state_dir."""
    from makoto.record.db import init_db
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
    from makoto.record import ledger as _ledger
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
    from makoto.record import ledger as _ledger
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
    """if makoto.record.db is absent, _dispatch.main() creates it on first call."""
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
    assert rc == 0
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
    assert rc == 0
    assert out == "", f"disabled pattern must not emit block JSON; got {out!r}"
    # only-fires audit policy: a missing audit.jsonl means ZERO patterns fired, which already
    # proves the disabled one did not. A regression that fired it would recreate the file with a
    # content.verifier_predicate_weakened row, flipping the any(...) below to True. Written this
    # way rather than under `if audit_path.exists():`, which SKIPPED the assertion entirely -- and
    # a disabled pattern writing no audit file is exactly the expected state, so the claim never
    # ran. Same reasoning, and same shape, as the gate.advance check further down this file.
    audit_path = state_dir / "audit.jsonl"
    rows = ([json.loads(l) for l in audit_path.read_text().splitlines() if l.strip()]
            if audit_path.exists() else [])
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
    from makoto.record import ledger
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
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
    try:
        row = ledger.read_key(conn, "src/auth.py")
    finally:
        conn.close()
    assert row is not None and row["kind"] == "touched", f"expected touched row; got {row!r}"


def test_dispatch_posttooluse_bash_records_ledger_value(tmp_path):
    """PostToolUse Bash -> a `value` ledger row keyed by the path token in the command."""
    import sqlite3
    from makoto.record import ledger
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
    conn = sqlite3.connect(str(state_dir / "makoto.record.db"))
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
    """Behavioral blocking pin for makoto.contract_order's Stop remainder guard (SPEC-5), driven
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


def test_dispatch_contract_order_gate_silent_after_locating_write_advances_the_plan(tmp_path):
    """The live-advance-wiring fix (2026-07-23): before this, Plan.mark_done/plan.persist_plan
    had zero live callers -- a declared plan could NEVER close, so gate.contract_order's Stop
    remainder blocked every turn for the rest of the session, forever, once any plan existed (see
    makoto/events.py's PostToolUse entry). Here a PostToolUse Write at the node's own `where`
    advances it to DONE, and the SAME Stop shape that blocks in the sibling test above (the plan
    left untouched) now passes clean."""
    state_dir = _setup_state(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "makoto-plan.jsonl").write_text(
        '{"what":"Write","passthrough":"auth.py","where":"auth.py","id":"n1"}\n'
    )
    session = "contract_order_advance"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    write = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
             "tool_name": "Write",
             "tool_input": {"file_path": "auth.py", "content": "def login(): ...\n"},
             "tool_response": {}}
    rc, out = _run_dispatch(state_dir, write)
    assert rc == 0 and out == "", "PostToolUse accumulation must never itself block"
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", f"contract_order must stay silent once the only declared node is advanced: {out}"


def test_dispatch_contract_order_gate_still_blocks_on_the_untouched_sibling_node(tmp_path):
    """Precision guard on the fix above: advancing ONE node of a two-node plan must not silently
    satisfy the OTHER (a resolve()-scoping regression would defeat the gate's whole purpose) --
    Stop still blocks, naming only the still-open sibling."""
    state_dir = _setup_state(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "makoto-plan.jsonl").write_text(
        '{"what":"Write","passthrough":"auth.py","where":"auth.py","id":"n1"}\n'
        '{"what":"Write","passthrough":"db.py","where":"db.py","id":"n2"}\n'
    )
    session = "contract_order_partial"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    write = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
             "tool_name": "Write",
             "tool_input": {"file_path": "auth.py", "content": "def login(): ...\n"},
             "tool_response": {}}
    rc, out = _run_dispatch(state_dir, write)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "contract_order must still block on the untouched sibling node"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "n2" in decision["reason"]
    assert "n1" not in decision["reason"]


def test_dispatch_contract_order_gate_blocks_after_a_live_mid_session_plan_write(tmp_path):
    """The live-declare-path fix (2026-07-23): before this, NOTHING let Claude declare a plan
    mid-session -- the only admission path was a `.claude/makoto-plan.jsonl` already sitting on
    disk BEFORE SessionStart fired. Here NO artifact exists at SessionStart at all; the plan is
    declared entirely via a live PostToolUse Write to the artifact path itself, and the same
    Stop remainder guard still blocks on its unfinished node."""
    state_dir = _setup_state(tmp_path)
    session = "contract_order_live_declare"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "makoto-plan.jsonl").write_text(
        '{"what":"Write","passthrough":"auth.py","where":"auth.py","id":"n1"}\n'
    )
    declare = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
               "tool_name": "Write",
               "tool_input": {"file_path": str(claude_dir / "makoto-plan.jsonl"),
                              "content": '{"what":"Write","passthrough":"auth.py","where":"auth.py","id":"n1"}\n'},
               "tool_response": {}}
    rc, out = _run_dispatch(state_dir, declare)
    assert rc == 0 and out == "", "declaring a plan must never itself block"
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "contract_order must block on the live-declared plan's open node"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "n1" in decision["reason"]


def test_dispatch_contract_order_gate_silent_after_live_declare_then_advance(tmp_path):
    """Full live lifecycle, no on-disk artifact ever needed before SessionStart: declare a plan
    via a mid-session Write to the artifact, advance its node via a Write to the node's own
    `where`, and Stop passes clean."""
    state_dir = _setup_state(tmp_path)
    session = "contract_order_live_full"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "makoto-plan.jsonl").write_text(
        '{"what":"Write","passthrough":"auth.py","where":"auth.py","id":"n1"}\n'
    )
    declare = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
               "tool_name": "Write",
               "tool_input": {"file_path": str(claude_dir / "makoto-plan.jsonl"),
                              "content": '{"what":"Write","passthrough":"auth.py","where":"auth.py","id":"n1"}\n'},
               "tool_response": {}}
    rc, out = _run_dispatch(state_dir, declare)
    assert rc == 0 and out == ""
    write = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
             "tool_name": "Write",
             "tool_input": {"file_path": "auth.py", "content": "def login(): ...\n"},
             "tool_response": {}}
    rc, out = _run_dispatch(state_dir, write)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", f"contract_order must stay silent after live declare + advance: {out}"


def test_dispatch_live_plan_write_malformed_content_fails_open_no_crash_no_block(tmp_path):
    """A malformed/non-falsifiable live plan write must declare NOTHING (fail-open) -- never
    crash the hook, never spuriously block on garbage content."""
    state_dir = _setup_state(tmp_path)
    session = "contract_order_live_malformed"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "makoto-plan.jsonl").write_text("not json at all")
    declare = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
               "tool_name": "Write",
               "tool_input": {"file_path": str(claude_dir / "makoto-plan.jsonl"),
                              "content": "not json at all"},
               "tool_response": {}}
    rc, out = _run_dispatch(state_dir, declare)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0 and out == "", "malformed live plan content must never manufacture a block"


def test_dispatch_live_plan_write_latest_wins_replaces_the_whole_plan(tmp_path):
    """A second live plan write REPLACES the whole plan (latest-wins, matching declare_plan's
    documented semantics) -- Stop blocks on the SECOND plan's node, not the first's."""
    state_dir = _setup_state(tmp_path)
    session = "contract_order_live_latest_wins"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    artifact = claude_dir / "makoto-plan.jsonl"
    artifact_path = str(artifact)
    artifact.write_text('{"what":"Write","passthrough":"a.py","where":"a.py","id":"n1"}\n')
    first = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
             "tool_name": "Write",
             "tool_input": {"file_path": artifact_path,
                            "content": '{"what":"Write","passthrough":"a.py","where":"a.py","id":"n1"}\n'},
             "tool_response": {}}
    rc, out = _run_dispatch(state_dir, first)
    assert rc == 0 and out == ""
    artifact.write_text('{"what":"Write","passthrough":"b.py","where":"b.py","id":"n2"}\n')
    second = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(tmp_path),
              "tool_name": "Write",
              "tool_input": {"file_path": artifact_path,
                             "content": '{"what":"Write","passthrough":"b.py","where":"b.py","id":"n2"}\n'},
              "tool_response": {}}
    rc, out = _run_dispatch(state_dir, second)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "Done for now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0 and out, "must block on the second (latest-wins) plan's node"
    decision = json.loads(out)
    assert "n2" in decision["reason"]
    assert "n1" not in decision["reason"]


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
    """The same canonical command in a settled PostToolUse deed certifies the action claim."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "fab_ok",
            "cwd": str(tmp_path),
            "tool_input": {"command": "pytest tests/zzz_unrun.py -q"},
            "tool_response": {"stdout": "1 passed", "stderr": "", "exitCode": 0}}
    _run_dispatch(state_dir, post)
    stop = {"hook_event_name": "Stop", "session_id": "fab_ok", "cwd": str(tmp_path),
            "last_assistant_message": "I ran `pytest tests/zzz_unrun.py -q` and it all passed."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", "the exact settled command should certify the action claim"


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


def test_dispatch_claimed_running_gate_blocks_after_recorded_failed_launch(tmp_path):
    """Behavioral blocking pin for gate.claimed_running THROUGH the real dispatch. A backgrounded
    launch recorded at PostToolUse as interrupted, then a Stop claim that the server is running ->
    the gate reads the most recently recorded process-lifecycle call from ctx.history -> BLOCKS live
    by default. Breaking _blocking_gate_ids() or the history wiring reddens THIS, proving the
    running claim stops the agent end-to-end, not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "run_block",
            "cwd": str(tmp_path),
            "tool_input": {"command": "npm run dev &"},
            "tool_response": {"interrupted": True}}
    rc, _ = _run_dispatch(state_dir, post)              # records the failed launch into history
    assert rc == 0
    stop = {"hook_event_name": "Stop", "session_id": "run_block", "cwd": str(tmp_path),
            "last_assistant_message": "I started the server. It is now running on port 3000."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "claimed_running gate must block a running claim over a recorded failed launch"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "direct error state" in decision["reason"]
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.claimed_running" in r.get("pattern_fires", []) for r in rows), \
        "the claimed_running fire must be audited"


def test_dispatch_claimed_shipped_gate_blocks_on_unbacked_remote_claim(tmp_path):
    """Behavioral blocking pin for gate.claimed_shipped through the real dispatcher: an immediate
    completed merge claim with no prior successful remote mutation must produce a block decision
    and an audit fire."""
    state_dir = _setup_state(tmp_path)
    stop = {"hook_event_name": "Stop", "session_id": "ship_block", "cwd": str(tmp_path),
            "last_assistant_message": "I merged the PR."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "claimed_shipped gate must block an unbacked completed remote-action claim"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "remote.merge" in decision["reason"]
    rows = [json.loads(line) for line in (state_dir / "audit.jsonl").read_text().splitlines()
            if line.strip()]
    assert any("gate.claimed_shipped" in row.get("pattern_fires", []) for row in rows), \
        "the claimed_shipped fire must be audited"


def test_dispatch_run_promised_gate_silent_on_the_very_turn_the_promise_is_made(tmp_path):
    """Grace-period proof for gate.claimed_running's forward-looking sibling, gate.run_promised:
    a run-intent promise must never block the SAME Stop it was made in. `history` structurally
    never contains the row for the Stop currently being evaluated, so there is nothing yet for
    this gate to read at the moment the promise is first made -- the earliest it can possibly fire
    is the NEXT Stop."""
    state_dir = _setup_state(tmp_path)
    session = "run_promise_grace"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    stop = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "I'll run the tests now."}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", f"a promise made THIS turn must never block THIS turn: {out}"


def test_dispatch_run_promised_gate_blocks_when_no_bash_call_follows_the_promise(tmp_path):
    """Behavioral blocking pin for gate.run_promised THROUGH the real dispatch. Turn 1 promises a
    run ("I'll run the tests now."); turn 2 ends with NO Bash call anywhere in between -> the gate
    reads the prior turn's own Stop row from ctx.history and BLOCKS live by default. Breaking
    _blocking_gate_ids() or the history wiring reddens THIS, proving an unfulfilled forward
    promise stops the agent end-to-end at the next turn, not merely emits a finding."""
    state_dir = _setup_state(tmp_path)
    session = "run_promise_block"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    stop1 = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
             "last_assistant_message": "I'll run the tests now."}
    rc, out = _run_dispatch(state_dir, stop1)
    assert rc == 0 and out == ""                     # grace period: turn 1 itself never blocks
    stop2 = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
             "last_assistant_message": "Here's a summary of what I found."}
    rc, out = _run_dispatch(state_dir, stop2)
    assert rc == 0
    assert out, "run_promised gate must block turn 2: turn 1's promise has no Bash evidence since"
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "run" in decision["reason"].lower()
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.run_promised" in r.get("pattern_fires", []) for r in rows), \
        "the run_promised fire must be audited"


def test_dispatch_run_promised_gate_silent_when_a_bash_call_discharges_it(tmp_path):
    """Control proving the gate DISCRIMINATES end-to-end (not fire-on-everything): the SAME
    forward promise, but a real Bash call happens before the next Stop -> discharged -> no
    block, regardless of whether the command's content matches the promised text (see the
    gate module's own docstring on why content-matching is deliberately out of scope)."""
    state_dir = _setup_state(tmp_path)
    session = "run_promise_discharged"
    start = {"hook_event_name": "SessionStart", "session_id": session, "cwd": str(tmp_path),
             "source": "startup"}
    rc, out = _run_dispatch(state_dir, start)
    assert rc == 0 and out == ""
    stop1 = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
             "last_assistant_message": "I'll run the tests now."}
    rc, out = _run_dispatch(state_dir, stop1)
    assert rc == 0 and out == ""
    bash = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": session,
            "cwd": str(tmp_path), "tool_input": {"command": "pytest -q"},
            "tool_response": {"exitCode": 0}}
    rc, out = _run_dispatch(state_dir, bash)
    assert rc == 0 and out == ""
    stop2 = {"hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
             "last_assistant_message": "Tests passed."}
    rc, out = _run_dispatch(state_dir, stop2)
    assert rc == 0
    assert out == "", f"a Bash call after the promise must discharge it: {out}"


def test_dispatch_named_test_gate_blocks_through_subagent_stop(tmp_path):
    """SubagentStop falsifier: the same fabricated named-test pass-claim that blocks through Stop
    (test_dispatch_named_test_gate_blocks_after_recorded_named_red above) must block IDENTICALLY
    when it arrives as a SubagentStop event — a sub-agent's own completion claim is checked by the
    same gates a main-thread Stop claim is checked by. Breaking the `hook_event in ("Stop",
    "SubagentStop")` branch in _dispatch.main() reddens this while leaving the Stop-path sibling
    test green, proving the SubagentStop route specifically."""
    state_dir = _setup_state(tmp_path)
    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "nt_sub",
            "agent_id": "named-test-agent",
            "cwd": str(tmp_path),
            "tool_input": {"command": "python -m pytest tests/ -q"},
            "tool_response": {"stdout": "FAILED tests/x.py::test_foo - AssertionError\n1 failed in 0.1s",
                              "stderr": "", "exitCode": 1}}
    rc, _ = _run_dispatch(state_dir, post)              # records the per-test red into history
    assert rc == 0
    subagent_stop = {"hook_event_name": "SubagentStop", "session_id": "nt_sub", "cwd": str(tmp_path),
                     "agent_id": "named-test-agent",
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
    advisory-only exception (DESIGN DECISION, 2026-07-05) must never block through SubagentStop
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
    (2026-07-05, DESIGN DECISION): it IS discovered (present in _blocking_gate_ids() like every other
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


def test_dispatch_relative_path_citation_gate_never_blocks_even_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.relative_path_citation (2026-07-09)
    fires (audited) but never blocks, even when its own condition holds -- a Stop turn whose
    last_assistant_message cites a non-absolute path."""
    state_dir = _setup_state(tmp_path)
    stop = {"hook_event_name": "Stop", "session_id": "relpath", "cwd": str(tmp_path),
            "last_assistant_message": "see checks/hollowTest.py:146 for the detector"}
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", "gate.relative_path_citation must NEVER block, even when it fires"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.relative_path_citation" in r.get("pattern_fires", []) for r in rows), \
        "the advisory fire must still be audited so it leaves a forensic trail"


def test_dispatch_plan_item_drift_gate_never_blocks_even_when_it_fires(tmp_path):
    """Behavioral pin, same shape as gate.self_wired's: gate.plan_item_drift (2026-07-09) fires
    (audited) but never blocks, even when a plan/task-labeled commitment is left open across
    two Stop turns."""
    state_dir = _setup_state(tmp_path)
    first = {"hook_event_name": "Stop", "session_id": "planitem", "cwd": str(tmp_path),
             "last_assistant_message": "I'll finish §9.3 after this push."}
    rc, out = _run_dispatch(state_dir, first)
    assert rc == 0
    second = {"hook_event_name": "Stop", "session_id": "planitem", "cwd": str(tmp_path),
              "last_assistant_message": "Moving on to other work for now."}
    rc, out = _run_dispatch(state_dir, second)
    assert rc == 0
    assert out == "", "gate.plan_item_drift must NEVER block, even when it fires"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("gate.plan_item_drift" in r.get("pattern_fires", []) for r in rows), \
        "the advisory fire must still be audited so it leaves a forensic trail"


def test_no_shadow_gate_every_gate_blocks():
    """Warning-tier-elimination invariant, STRUCTURAL after the gates/ package cutover: may_block
    <=> reaches the decision pipeline. The pipeline-eligible set DERIVES from
    `Check.may_block` via `load_checks(edge="Stop")` (2026-07-10, retiring load_stopchecks()/GATE),
    so a gate cannot be wired without reaching the pipeline (no audit-only shadow tier) and cannot
    reach it without being explicitly marked may_block=True. The former check.quantity shadow gate
    was CUT 2026-06-02 — it could not block FP-safely. A future shadow gate (discoverable but
    routed around _blocking_gate_ids(), or wired into run_stop_checks without may_block) turns
    this red."""
    from makoto.substrate._loader import load_checks
    from makoto._dispatch import _blocking_gate_ids
    live = [c for c in load_checks(edge="Stop") if c.may_block]
    discovered = {c.id for c in live}
    assert discovered == {"gate.completion", "gate.advance", "gate.green_claim", "gate.dropped",
                          "gate.fabricated_action", "gate.named_test", "gate.stale_pass",
                          "gate.liveness",     # liveness folded in from the collapsed close-check tier
                          "gate.hollow_test",  # HOLLOWED-class detector (SPIRIT.md §4), same split as liveness
                          "gate.canon",        # ported agnostic Stop primitives canon.timeout/canon.recur
                          "gate.contract_order",   # SPEC-5 (Makoto absorbs Assay): the plan's Stop
                                                      # remainder guard
                          "gate.self_wired",   # advisory-tier exception (2026-07-05); still
                                               # discovered <=> in _blocking_gate_ids(), just never
                                               # emits level="error" so never actually blocks
                          "gate.relative_path_citation",  # advisory-tier (2026-07-09): same shape
                          "gate.plan_item_drift",         # advisory-tier (2026-07-09): same shape
                          "gate.claimed_running",  # agnostic claim-vs-recorded-Bash-evidence gate (2026-07-23)
                          "gate.run_promised",  # claimed_running's forward-looking sibling (2026-07-23)
                          "gate.claimed_shipped"}  # completed remote-mutation claim-vs-record gate
    # may_block <=> reaches the pipeline: the set is not hand-maintained, it IS the may_block ids.
    assert set(_blocking_gate_ids()) == discovered
    # The check.quantity / claim_check capability no longer EXISTS: no live gate's run adapter
    # references it, and the package exposes no such callable (re-adding it as a gate turns this
    # red). No separate `.fn` attribute anymore (GATE/StopCheck retired) -- introspect the actual
    # function names each `run` closure/adapter references via its code object.
    referenced = {name for c in live for name in c.run.__code__.co_names}
    assert "claim_check" not in referenced
    assert "dropped_gate" in referenced       # live -> discovered + reaches the pipeline


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

    gate.self_wired (2026-07-05, DESIGN DECISION) is the one documented exception: it IS discovered
    (and so appears in _blocking_gate_ids() by the discovered<=>live<=>blocking wiring), but it
    ships at level="advisory", never "error" — it structurally CANNOT cause a block decision, so a
    "...gate_blocks" test for it would assert something false. Its behavioral pin instead lives in
    test_dispatch_self_wired_gate_never_blocks_even_when_it_fires (this file), which proves the
    opposite claim: it fires (audited) and never blocks."""
    from pathlib import Path as _P
    from makoto._dispatch import _blocking_gate_ids
    _ADVISORY_EXEMPT = {"gate.self_wired",
                        "gate.relative_path_citation", "gate.plan_item_drift"}
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
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
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
    from makoto.core.schema import PreCheck
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
    from makoto.core.schema import PreCheck
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
    assert rc == 0
    assert out, "content.fabricated_commit_sha (fabricated SHA) must fire on a real history slice -> block JSON"
    assert json.loads(out)["decision"] == "block"
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert any("content.fabricated_commit_sha" in r.get("pattern_fires", []) for r in rows), \
        "the content.fabricated_commit_sha fire must be recorded (history slice was actually returned)"


def test_dispatch_decision_carries_retry_hint_when_finding_has_one(tmp_path):
    """PreCheck content.verifier_predicate_weakened produces a truthy retry_hint (via `_jit_hint`). SPEC-5 Task 8: the live
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
    assert rc == 0
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines() if l.strip()]
    assert rows, "the error-level fire must record an audit row"
    fire_rows = [r for r in rows if "content.verifier_predicate_weakened" in r.get("pattern_fires", [])]
    assert fire_rows, "expected a content.verifier_predicate_weakened fire row"
    assert fire_rows[0].get("exit_code") == 2, (
        "an error-level finding must record exit_code=2 in the audit row; "
        f"got {fire_rows[0].get('exit_code')!r}"
    )


def _run_raw(state_dir, raw: bytes) -> tuple[int, str, str]:
    """Invoke the dispatcher with RAW bytes on stdin, bypassing json.dumps.

    _run_dispatch serialises a dict, so it cannot express the two cases this test is about --
    no bytes at all, and bytes that are not JSON.
    """
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch"],
        input=raw, capture_output=True, env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def test_an_empty_payload_and_an_unparseable_one_get_different_reasons(tmp_path):
    """Same disposition, different reason -- because the operator has to act on the difference.

    Found by driving the dispatcher as Claude Code drives it. Both cases loud-allow, which is the
    deliberate fail-mode (a truncated pipe must never block agent work) and is NOT changed. But
    both recorded "stdin was not valid JSON", including when no bytes arrived at all -- telling
    the reader the payload was invalid when there had been no payload.

    They need different fixes: no bytes is the hook invoked with nothing attached, a wiring fault
    that recurs on every event; unparseable bytes is a pipe cut mid-write, which is transient.
    """
    state = _setup_state(tmp_path)

    code, stdout, stderr = _run_raw(state, b"")
    assert code == 0, stderr                      # allow: the fail-mode is unchanged
    assert stdout == ""
    assert "stdin was empty" in stderr, stderr
    assert "no payload arrived at all" in stderr, stderr

    code, stdout, stderr = _run_raw(state, b"not json at all {{{")
    assert code == 0, stderr
    assert "stdin was not valid JSON" in stderr, stderr
    assert "stdin was empty" not in stderr, stderr

    # The field is pattern_id, read from a real fact rather than guessed. An earlier draft of
    # this test asserted on fact["kind"], which does not exist: every row returned None, so the
    # count was 0 and the assertion failed for a reason unrelated to the behaviour under test.
    # A test that guesses a schema can fail while the code is right -- or pass while it is wrong.
    facts = _dispatch_facts(state)
    ids = [fact.get("pattern_id") for fact in facts]
    assert ids.count("dispatch.unparseable_payload") == 2, facts
    messages = " | ".join(fact.get("exc_message", "") for fact in facts)
    assert "stdin was empty" in messages, facts
    assert "stdin was not valid JSON" in messages, facts


def test_a_valid_non_object_payload_still_fails_closed(tmp_path):
    """The control. Distinguishing empty from unparseable must not soften the tamper-shaped case.

    A truncated pipe yields INVALID json, never valid-non-object, so valid JSON that is not an
    object is anomalous rather than transient and blocks at exit 2. If this ever joins the
    loud-allow branch, the fail-mode has been widened by accident.
    """
    state = _setup_state(tmp_path)
    code, _, stderr = _run_raw(state, b'"a valid json string, not an object"')
    assert code == 2, stderr
    assert "non_object_payload" in stderr, stderr
