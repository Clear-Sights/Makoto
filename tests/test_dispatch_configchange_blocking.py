"""D5 (docs/DEFERRED.md, owner-authorized 2026-07-08): the BLOCKING tier of
`makoto/_dispatch_configchange.py` -- fires ONLY on evidenced strips (a manifest-hit, or an
observed had->lost transition), never on a bare "stripped" reading with no prior evidence (the
"never wired" case stays advisory forever -- see `test_dispatch_configchange.py`).

Same subprocess-invocation convention as that file: spawn `python -m makoto._dispatch_configchange`
with `MAKOTO_STATE_DIR` pointed at a tmp dir, stdin fed a JSON payload, assert on
`(returncode, stdout)` and `audit.jsonl`.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import makoto as _makoto_under_test

_PKG_PARENT = str(Path(_makoto_under_test.__file__).resolve().parent.parent)


def _run_json(state_dir, payload) -> tuple[int, bytes]:
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch_configchange"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=_PKG_PARENT,
    )
    return proc.returncode, proc.stdout


def _audit_rows(state_dir) -> list:
    f = Path(state_dir) / "audit.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]


def _settings(pre=True, post=True, stop=True):
    def _entry(wired):
        cmd = "python3 -m makoto._dispatch" if wired else "python3 -m ventura.adapters.hook_bridge"
        return {"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}

    return {"hooks": {
        "PreToolUse": [_entry(pre)],
        "PostToolUse": [_entry(post)],
        "Stop": [_entry(stop)],
    }}


def _write_settings(tmp_path, name="settings.json", **wiring):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    p = claude_dir / name
    p.write_text(json.dumps(_settings(**wiring)))
    return str(p)


def _payload(tmp_path, settings_path, session_id="cc"):
    return {
        "hook_event_name": "ConfigChange",
        "session_id": session_id,
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": settings_path,
    }


# --- manifest-hit: a stripped path the installer itself recorded as wired -----------------------

def test_manifest_hit_on_stripped_path_blocks(tmp_path):
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=False, post=False, stop=False)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "configchange_manifest.json").write_text(
        json.dumps([str(Path(settings_path).resolve())]))
    rc, out = _run_json(state_dir, _payload(tmp_path, settings_path))
    assert rc == 0
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert decision["reason"]
    rows = _audit_rows(state_dir)
    assert len(rows) == 1
    assert rows[0]["pattern_fires"] == ["gate.configchange_transition"]
    assert rows[0]["findings"][0]["level"] == "error"


def test_manifest_present_but_this_path_not_in_it_stays_advisory(tmp_path):
    """A manifest exists (some OTHER path is wired) but does not name THIS config_path -- must
    not block on a manifest that simply doesn't mention it."""
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=False, post=False, stop=False)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "configchange_manifest.json").write_text(
        json.dumps([str(tmp_path / "some" / "other" / "settings.json")]))
    rc, out = _run_json(state_dir, _payload(tmp_path, settings_path))
    assert rc == 0
    assert out == b""
    rows = _audit_rows(state_dir)
    assert rows[0]["pattern_fires"] == ["gate.configchange_advisory"]


# --- transition: a path observed wired on a PRIOR evaluation, now stripped -----------------------

def test_had_hooks_then_stripped_transition_blocks(tmp_path):
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=True, post=True, stop=True)
    # First evaluation: clean/wired -- no fire, but must SAVE the had_hooks=True snapshot.
    rc1, out1 = _run_json(state_dir, _payload(tmp_path, settings_path, session_id="s1"))
    assert rc1 == 0 and out1 == b""
    assert _audit_rows(state_dir) == []
    snap = json.loads((state_dir / "configchange_snapshots.json").read_text())
    resolved = str(Path(settings_path).resolve())
    assert snap[resolved]["had_hooks"] is True

    # Strip it, second evaluation of the SAME path: now must BLOCK (a real had->lost transition).
    Path(settings_path).write_text(json.dumps(_settings(pre=False, post=False, stop=False)))
    rc2, out2 = _run_json(state_dir, _payload(tmp_path, settings_path, session_id="s2"))
    assert rc2 == 0
    decision = json.loads(out2)
    assert decision["decision"] == "block"
    rows = _audit_rows(state_dir)
    assert len(rows) == 1
    assert rows[0]["pattern_fires"] == ["gate.configchange_transition"]


def test_never_wired_stays_advisory_even_across_repeated_stripped_evaluations(tmp_path):
    """A path that has NEVER been observed with hooks present (no manifest entry either) must
    stay advisory FOREVER, no matter how many times it evaluates as stripped -- the whole
    FP-safety property this tier depends on."""
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=False, post=False, stop=False)
    for i in range(3):
        rc, out = _run_json(state_dir, _payload(tmp_path, settings_path, session_id=f"s{i}"))
        assert rc == 0
        assert out == b"", f"iteration {i} must never block"
    rows = _audit_rows(state_dir)
    assert len(rows) == 3
    assert all(r["pattern_fires"] == ["gate.configchange_advisory"] for r in rows)


def test_clean_evaluation_of_unrecorded_path_saves_snapshot_without_firing(tmp_path):
    """A clean/wired evaluation must still persist had_hooks=True for a path with no PRIOR
    snapshot (not just update an existing one) -- proven by a subsequent strip then blocking."""
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=True, post=True, stop=True)
    rc, out = _run_json(state_dir, _payload(tmp_path, settings_path))
    assert rc == 0 and out == b""
    snap_path = state_dir / "configchange_snapshots.json"
    assert snap_path.exists()
    snap = json.loads(snap_path.read_text())
    assert snap[str(Path(settings_path).resolve())]["had_hooks"] is True


# --- policy_settings: never blockable, confirmed still true under the blocking tier --------------

def test_policy_settings_never_blocks_even_with_manifest_hit(tmp_path):
    """configchange_verdict's own _APPLICABLE_SOURCES excludes policy_settings entirely
    (fires=False unconditionally) -- confirm the blocking tier inherits that, even with a
    manifest entry present for the same path."""
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=False, post=False, stop=False)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "configchange_manifest.json").write_text(
        json.dumps([str(Path(settings_path).resolve())]))
    payload = {
        "hook_event_name": "ConfigChange", "session_id": "cc_policy", "cwd": str(tmp_path),
        "config_source": "policy_settings", "config_path": settings_path,
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    assert _audit_rows(state_dir) == []
