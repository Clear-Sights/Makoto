"""dispatch-level coverage for issue #70: a pre-2.4.0 chain row containing U+2028 must not be
reported as dispatch.chain_tamper, and its own classification (dispatch.legacy_row_hash) must
follow the same once-per-session marker pattern as _note_host_dialect (tests/test_hostdialect.py's
test_dispatch_notes_dialect_once_per_session). Kept in its own module rather than folded into
tests/test_dispatch.py's chain-self-verify block so this fixture-heavy addition stays easy to
diff against that file's existing chain tests.
"""
import json
from pathlib import Path

from tests.conftest import _setup_state, _run_dispatch


def _chain_path(state_dir) -> Path:
    return Path(state_dir) / "chain.jsonl"


def _dispatch_facts(state_dir) -> list:
    f = Path(state_dir) / "dispatch_errors.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]


def _append_legacy_chain_row(state_dir, value: str):
    """A genuine pre-2.4.0 row: hashed with the retired norm_sha256(prev_hash + canonical(row))
    construction, never through ledger.append() -- append() only ever writes the CURRENT
    construction, so reproducing the old one here is the only way to get one on disk for a test."""
    from makoto.state import ledger as _ledger
    existing = _ledger.read(root=Path(state_dir))
    prev_hash = existing[-1].get("row_hash", "") if existing else ""
    row = {"kind": "value", "key": "bash", "value": value, "prev_hash": prev_hash, "status": "open"}
    row["row_hash"] = _ledger._legacy_row_hash(prev_hash, row)
    with open(_chain_path(state_dir), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")


def test_dispatch_legacy_row_hash_not_reported_as_chain_tamper(tmp_path, monkeypatch):
    """A chain row written pre-2.4.0 and carrying U+2028 -- the one character the old and new
    hash constructions disagree on -- must NOT surface as dispatch.chain_tamper. It is
    authentic, classified distinctly instead (dispatch.legacy_row_hash)."""
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    from makoto.state import ledger as _ledger
    _ledger.append({"kind": "verdict", "key": "a"})
    _append_legacy_chain_row(state_dir, "ok" + chr(0x2028) + "next")

    payload = {
        "hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello"},
    }
    rc, out = _run_dispatch(state_dir, payload)
    facts = _dispatch_facts(state_dir)
    assert not any(f.get("pattern_id") == "dispatch.chain_tamper" for f in facts), facts
    assert any(f.get("pattern_id") == "dispatch.legacy_row_hash" for f in facts), facts


def test_dispatch_notes_legacy_row_hash_once_per_session(tmp_path, monkeypatch):
    """Same marker-pattern dedup as host_dialect (_note_host_dialect): a chain carrying a legacy
    row must not put dispatch.legacy_row_hash on EVERY dispatch for the rest of its life."""
    state_dir = _setup_state(tmp_path)
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_dir))
    from makoto.state import ledger as _ledger
    _ledger.append({"kind": "verdict", "key": "a"})
    _append_legacy_chain_row(state_dir, "ok" + chr(0x2028) + "next")

    payload = {
        "hook_event_name": "PreToolUse", "session_id": "c9", "cwd": "/tmp",
        "tool_input": {"file_path": "/tmp/unrelated.txt", "content": "hello"},
    }
    for _ in range(2):
        rc, out = _run_dispatch(state_dir, payload)
        assert rc == 0
    markers = list((Path(state_dir) / "legacy_row_hash").glob("*.json"))
    assert len(markers) == 1
    facts = _dispatch_facts(state_dir)
    n = sum(1 for f in facts if f.get("pattern_id") == "dispatch.legacy_row_hash")
    assert n == 1, f"legacy_row_hash noted {n} times; must be once per session"
