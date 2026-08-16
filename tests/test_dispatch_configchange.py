"""End-to-end subprocess tests for `makoto/_dispatch_configchange.py` (the ConfigChange hook
adapter). Mirrors `test_dispatch.py`'s subprocess-invocation convention: spawn
`python -m makoto._dispatch_configchange` with `MAKOTO_STATE_DIR` pointed at a tmp dir and stdin
fed a JSON payload, then assert on `(returncode, stdout)` and on `audit.jsonl`'s contents.

Like `test_configchange_verdict.py`, every payload here is CONSTRUCTED against hand-built payload
shapes that match the event's documented schema, not against a live event stream (see this
module's own docstring for what a live-fire probe found).

D5 (owner-authorized, 2026-07-08): this module now has TWO tiers. Every test in THIS file uses a
fresh, unrecorded `tmp_path`-based `config_path` -- no manifest entry, no prior snapshot -- so
they exercise the ADVISORY tier exclusively and correctly stay non-blocking; that is a property
of the FIXTURES here (no blocking evidence exists for any of them), not a structural "this module
can never block" guarantee. `test_dispatch_configchange_blocking.py` covers the BLOCKING tier
(manifest-hit, had->lost transition) with its own dedicated fixtures.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import makoto as _makoto_under_test

# The subprocess must import THE SAME makoto these tests were collected against. `python -m`
# prepends its cwd to sys.path, so cwd must be the parent of the actually-imported package —
# never a fixed repo-relative hop (the old `Path(__file__).parent.parent.parent` encoded the
# monorepo layout, and in any other checkout shape it can land on a directory containing some
# OTHER `makoto/` — a sibling clone of a different version — silently testing the wrong code).
_PKG_PARENT = str(Path(_makoto_under_test.__file__).resolve().parent.parent)


def _run(state_dir, raw_stdin: bytes) -> tuple[int, bytes]:
    """invoke `python -m makoto._dispatch_configchange` with raw bytes on stdin;
    return (exit_code, stdout_bytes)."""
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch_configchange"],
        input=raw_stdin,
        capture_output=True,
        env=env,
        cwd=_PKG_PARENT,
    )
    return proc.returncode, proc.stdout


def _run_json(state_dir, payload, extra_env: dict | None = None) -> tuple[int, bytes]:
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
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


def _write_settings(tmp_path, **wiring):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.json").write_text(json.dumps(_settings(**wiring)))
    return str(claude_dir / "settings.json")


# --- basic fail-open shapes -----------------------------------------------------------------------

def test_unparseable_stdin_exits_0_empty_stdout_no_audit_row(tmp_path):
    state_dir = tmp_path / "makoto_state"
    rc, out = _run(state_dir, b"not json{{{")
    assert rc == 0
    assert out == b""
    assert _audit_rows(state_dir) == []


def test_non_dict_json_payload_exits_0_empty_stdout_no_audit_row(tmp_path):
    state_dir = tmp_path / "makoto_state"
    for raw in (b'["a", "list"]', b'"a bare string"', b"null", b"42"):
        rc, out = _run(state_dir, raw)
        assert rc == 0, raw
        assert out == b"", raw
    assert _audit_rows(state_dir) == []


# --- clean, fully-wired event: never fires ---------------------------------------------------------

def test_clean_fully_wired_project_settings_event_no_fire(tmp_path):
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=True, post=True, stop=True)
    payload = {
        "hook_event_name": "ConfigChange",
        "session_id": "cc1",
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": settings_path,
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    assert _audit_rows(state_dir) == []


# --- full simultaneous strip: fires, but STILL empty stdout / exit 0 -------------------------------

def test_full_strip_fires_advisory_audit_row_but_stdout_stays_empty(tmp_path):
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=False, post=False, stop=False)
    payload = {
        "hook_event_name": "ConfigChange",
        "session_id": "cc_full_strip",
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": settings_path,
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b"", "firing must never surface on stdout"
    rows = _audit_rows(state_dir)
    assert len(rows) == 1
    row = rows[0]
    assert row["pattern_fires"] == ["gate.configchange_advisory"]
    assert row["exit_code"] == 0
    assert row["hook_kind"] == "ConfigChange"
    assert row["event"] == "live.config_change"
    assert row["session_id"] == "cc_full_strip"
    assert row["tool_name"] == ""
    assert len(row["findings"]) == 1
    finding = row["findings"][0]
    assert finding["pattern_id"] == "gate.configchange_advisory"
    assert finding["level"] == "advisory"
    assert finding["file"] == settings_path
    assert finding["message"]


# --- partial strip: fires, same shape ---------------------------------------------------------------

def test_partial_strip_fires_advisory_audit_row(tmp_path):
    state_dir = tmp_path / "makoto_state"
    settings_path = _write_settings(tmp_path, pre=True, post=True, stop=False)
    payload = {
        "hook_event_name": "ConfigChange",
        "session_id": "cc_partial",
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": settings_path,
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    rows = _audit_rows(state_dir)
    assert len(rows) == 1
    assert rows[0]["pattern_fires"] == ["gate.configchange_advisory"]
    assert rows[0]["findings"][0]["level"] == "advisory"
    assert "Stop" in rows[0]["findings"][0]["message"]


# --- non-applicable config_source values: never fire, even fully stripped --------------------------

def test_non_applicable_config_sources_never_fire_even_when_stripped(tmp_path):
    settings_path_for = {}
    for source in ("user_settings", "policy_settings", "skills"):
        state_dir = tmp_path / f"state_{source}"
        stripped_path = tmp_path / source
        stripped_path.mkdir(parents=True, exist_ok=True)
        settings_file = stripped_path / "settings.json"
        settings_file.write_text(json.dumps(_settings(pre=False, post=False, stop=False)))
        payload = {
            "hook_event_name": "ConfigChange",
            "session_id": f"cc_{source}",
            "cwd": str(tmp_path),
            "config_source": source,
            "config_path": str(settings_file),
        }
        rc, out = _run_json(state_dir, payload)
        assert rc == 0, source
        assert out == b"", source
        assert _audit_rows(state_dir) == [], source


# --- content unavailable / malformed behind config_path: fail open, no audit row -------------------

def test_missing_config_path_file_fails_open_no_audit_row(tmp_path):
    state_dir = tmp_path / "makoto_state"
    payload = {
        "hook_event_name": "ConfigChange",
        "session_id": "cc_missing_file",
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": str(tmp_path / "does_not_exist" / "settings.json"),
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    assert _audit_rows(state_dir) == []


def test_malformed_json_content_fails_open_no_audit_row(tmp_path):
    state_dir = tmp_path / "makoto_state"
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    bad = claude_dir / "settings.json"
    bad.write_text("{not valid json")
    payload = {
        "hook_event_name": "ConfigChange",
        "session_id": "cc_malformed",
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": str(bad),
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    assert _audit_rows(state_dir) == []


def test_non_dict_json_content_fails_open_no_audit_row(tmp_path):
    state_dir = tmp_path / "makoto_state"
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    bad = claude_dir / "settings.json"
    bad.write_text(json.dumps([1, 2, 3]))
    payload = {
        "hook_event_name": "ConfigChange",
        "session_id": "cc_non_dict",
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": str(bad),
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    assert _audit_rows(state_dir) == []


def test_missing_config_source_and_config_path_keys_fails_open_no_audit_row(tmp_path):
    """config_source absent -> not applicable in configchange_verdict -> never fires."""
    state_dir = tmp_path / "makoto_state"
    payload = {"hook_event_name": "ConfigChange", "session_id": "cc_no_keys", "cwd": str(tmp_path)}
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    assert _audit_rows(state_dir) == []


# --- relative config_path resolves against cwd ------------------------------------------------------

def test_relative_config_path_resolves_against_payload_cwd(tmp_path):
    state_dir = tmp_path / "makoto_state"
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").write_text(json.dumps(_settings(pre=False)))
    payload = {
        "hook_event_name": "ConfigChange",
        "session_id": "cc_relative",
        "cwd": str(tmp_path),
        "config_source": "project_settings",
        "config_path": ".claude/settings.json",   # relative -> must join against cwd
    }
    rc, out = _run_json(state_dir, payload)
    assert rc == 0
    assert out == b""
    rows = _audit_rows(state_dir)
    assert len(rows) == 1
    assert "PreToolUse" in rows[0]["findings"][0]["message"]


# --- THE single most important test: advisory-never-blocking invariant across a wide input battery -

def test_advisory_never_blocks_across_varied_payload_battery(tmp_path):
    """Run ~10 varied constructed payloads (clean, stripped, malformed, non-applicable, missing
    keys, wrong types, adversarial garbage) through the adapter and assert stdout is EMPTY and exit
    code is 0 for every single one -- NONE of these paths have a manifest entry or a prior
    snapshot, so all correctly stay advisory-only (see `test_dispatch_configchange_blocking.py`
    for the fixtures that DO carry blocking evidence)."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    clean_settings = claude_dir / "clean_settings.json"
    clean_settings.write_text(json.dumps(_settings()))
    stripped_settings = claude_dir / "stripped_settings.json"
    stripped_settings.write_text(json.dumps(_settings(pre=False, post=False, stop=False)))
    malformed_settings = claude_dir / "malformed_settings.json"
    malformed_settings.write_text("{not valid json at all")

    raw_battery: list[bytes] = [
        b"",                                  # empty stdin
        b"   ",                               # whitespace-only stdin
        b"{{{not json at all",                # garbage
        b"null",
        b"true",
        b"3.14",
        b'"just a string"',
        b'{"config_source": "project_settings"}',                       # missing config_path
        b'{"config_path": "/nowhere"}',                                 # missing config_source
        b'{"config_source": 42, "config_path": null}',                  # wrong types
        b'{"config_source": "project_settings", "config_path": "/nowhere/at/all/settings.json"}',
    ]
    json_battery: list[dict] = [
        {"hook_event_name": "ConfigChange", "cwd": str(tmp_path),
         "config_source": "project_settings", "config_path": str(clean_settings)},
        {"hook_event_name": "ConfigChange", "cwd": str(tmp_path),
         "config_source": "project_settings", "config_path": str(stripped_settings)},
        {"hook_event_name": "ConfigChange", "cwd": str(tmp_path),
         "config_source": "project_settings", "config_path": str(malformed_settings)},
        {"hook_event_name": "ConfigChange", "cwd": str(tmp_path),
         "config_source": "user_settings", "config_path": str(stripped_settings)},
        {"hook_event_name": "ConfigChange", "cwd": str(tmp_path),
         "config_source": "policy_settings", "config_path": str(stripped_settings)},
        {"hook_event_name": "ConfigChange", "cwd": str(tmp_path),
         "config_source": "skills", "config_path": str(stripped_settings)},
        {"hook_event_name": "ConfigChange", "cwd": str(tmp_path),
         "config_source": "bogus_unknown_source", "config_path": str(stripped_settings)},
        {"hook_event_name": "ConfigChange"},   # no cwd, no config_source, no config_path at all
        {},                                    # totally empty object
        {"decision": "block", "config_source": "project_settings",
         "config_path": str(stripped_settings), "cwd": str(tmp_path)},   # adversarial: pre-baked block key
    ]

    state_dir = tmp_path / "battery_state"
    for i, raw in enumerate(raw_battery):
        rc, out = _run(state_dir / f"raw_{i}", raw)
        assert rc == 0, (i, raw)
        assert out == b"", (i, raw, out)

    for i, payload in enumerate(json_battery):
        rc, out = _run_json(state_dir / f"json_{i}", payload)
        assert rc == 0, (i, payload)
        assert out == b"", (i, payload, out)
