"""CI guard: every LIVE-dispatched finding carries its provenance (source_event_id).

This is the completeness oracle for Task 6. Provenance is stamped CENTRALLY at the
dispatch boundary (`_dispatch._run_predicates` for predicate findings, `main()` for
gate findings) via `dataclasses.replace(finding, source_event_id=event_id)`. These two
tests drive the real `python -m makoto._dispatch` end-to-end and assert the recorded
finding's `source_event_id` equals the actual `events.id` it came from — non-zero AND
correct. If the central stamp is ever removed or bypassed (a finding emitted without
provenance), `source_event_id` stays 0 and these go red — so a missed site can't ship
silently. Covers both finding-producing paths (predicate + gate).
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


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


def _only_event_id(state_dir) -> int:
    """the single hook event's id — _ingest_event is the only writer of `events`, so a
    fresh db has exactly one row after one dispatch. Returned to assert the stamp is the
    RIGHT event, not merely non-zero."""
    conn = sqlite3.connect(str(state_dir / "makoto.db"))
    try:
        ids = [r[0] for r in conn.execute("SELECT id FROM events").fetchall()]
    finally:
        conn.close()
    assert len(ids) == 1, f"expected exactly one hook event, got {ids}"
    return ids[0]


def _recorded_findings(state_dir) -> list[dict]:
    rows = [json.loads(l) for l in (state_dir / "audit.jsonl").read_text().splitlines()
            if l.strip()]
    return [f for r in rows for f in r.get("findings", [])]


def test_predicate_finding_carries_source_event_id(tmp_path):
    """A live predicate fire (pattern 1.1) records a finding stamped with its events.id."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "session_id": "prov_pred",
        "cwd": "/tmp",
        "tool_input": {
            "file_path": "constitution/integrity/checks/myverifier.py",
            "content": 'def check(x):\n    return x.startswith("ok")\n',
        },
    }
    rc, out = _run_dispatch(state_dir, payload)
    # SPEC-5 Task 8: a PreToolUse block renders wire.py's real Pre shape (deny), not a literal
    # "block" substring.
    assert rc == 0 and '"deny"' in out, f"pattern 1.1 should fire; got rc={rc} out={out!r}"
    findings = _recorded_findings(state_dir)
    assert findings, "expected a recorded predicate finding"
    eid = _only_event_id(state_dir)
    assert eid != 0
    assert all(f["source_event_id"] == eid for f in findings), (
        "every live-dispatched finding must carry the events.id it came from; "
        f"got {[f['source_event_id'] for f in findings]} != {eid}"
    )


def test_gate_finding_carries_source_event_id(tmp_path):
    """A gate fire (completion gate on an unbacked production claim) is recorded with its
    events.id too — the second finding-producing path is also stamped. Pinned in shadow
    (MAKOTO_DISABLE_GATES=1) so this asserts provenance on the AUDIT path independently of
    the live block behavior."""
    state_dir = _setup_state(tmp_path)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "prov_gate",
        "cwd": str(tmp_path),  # the cited file definitely does not exist under here
        "last_assistant_message": "Done - added rate limiting to src/nonexistent_zzz.py",
    }
    rc, out = _run_dispatch(state_dir, payload, extra_env={"MAKOTO_DISABLE_GATES": "1"})
    assert rc == 0 and out == "", "shadow gate must audit without blocking"
    gate_findings = [f for f in _recorded_findings(state_dir)
                     if f["pattern_id"].startswith("gate.")]
    assert gate_findings, "expected a shadow gate finding in the audit log"
    eid = _only_event_id(state_dir)
    assert eid != 0
    assert all(f["source_event_id"] == eid for f in gate_findings), (
        "every gate finding must carry the Stop event's id; "
        f"got {[f['source_event_id'] for f in gate_findings]} != {eid}"
    )
