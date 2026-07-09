"""makoto.checks.forbiddenLocation -- re-homed from Assay's test_forbidden_location.py onto
Makoto's predicate contract (SPEC-5 Task 5). Fast, direct `predicate(...)` calls, no subprocess.
"""
from __future__ import annotations

from makoto.checks.forbiddenLocation import predicate
from makoto.core.schema import PreCheck

_PAT = PreCheck(
    id="event.forbidden_location",
    fire_level="error",
    description="forbidden location",
    retry_hint="do not write there",
)


def _evt(tool_name, tool_input, cwd=None):
    evt = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    if cwd is not None:
        evt["cwd"] = cwd
    return evt


def _write(file_path, cwd=None, content="x"):
    return _evt("Write", {"file_path": file_path, "content": content}, cwd=cwd)


def _edit(file_path, cwd=None):
    return _evt("Edit", {"file_path": file_path, "old_string": "a", "new_string": "b"}, cwd=cwd)


def _multiedit(file_path, cwd=None):
    return _evt("MultiEdit", {"file_path": file_path, "edits": [{"old_string": "a", "new_string": "b"}]}, cwd=cwd)


def _notebookedit(notebook_path, cwd=None):
    return _evt("NotebookEdit", {"notebook_path": notebook_path, "new_source": "print(1)"}, cwd=cwd)


def _reason(evt):
    f = predicate(current_event=evt, history=[], pattern=_PAT, conn=None)
    assert f is not None, f"expected a fire, got a clean pass for {evt!r}"
    return f.message


def _clean(evt):
    f = predicate(current_event=evt, history=[], pattern=_PAT, conn=None)
    assert f is None, f"expected a clean pass, got fired: {f}"


# --- makoto's own control-plane FILES -----------------------------------------------------------

def test_denies_write_to_claude_settings_json():
    assert "settings.json" in _reason(_write("/repo/.claude/settings.json"))


def test_denies_edit_to_claude_settings_local_json():
    assert "settings.local.json" in _reason(_edit("/repo/.claude/settings.local.json"))


def test_denies_multiedit_to_settings_json_GAP_fix():
    """CONFIRMED-BUG regression (Assay eval): MultiEdit must be judged too, not just Write/Edit."""
    assert "settings.json" in _reason(_multiedit("/repo/.claude/settings.json"))


def test_allows_unrelated_projects_own_settings_json():
    """EXACT (parent-segment, basename) pair -- a settings.json NOT under .claude/ is not makoto's."""
    _clean(_write("/repo/config/settings.json", cwd="/repo"))


# --- protected system / credential DIRECTORIES ---------------------------------------------------

def test_denies_write_under_dot_ssh():
    assert "protected-directory" in _reason(_write("/root/.ssh/authorized_keys"))


def test_silent_on_substring_lookalike_not_exact_segment():
    """'etc' must not match 'etcetera.md' -- exact segment membership, never substring."""
    _clean(_write("/repo/etcetera.md", cwd="/repo"))


# --- shell-rc FILES -------------------------------------------------------------------------------

def test_denies_edit_to_bashrc():
    assert "shell-rc" in _reason(_edit("/home/user/.bashrc"))


# --- credential BASENAMES (Write/MultiEdit only) -------------------------------------------------

def test_denies_write_to_id_rsa():
    assert "credential-basename" in _reason(_write("/home/user/.ssh/id_rsa".replace(".ssh/", "")))


def test_edit_to_credential_basename_is_not_gated_by_this_family():
    """credential-basename is Write/MultiEdit only per Assay's own scope -- an Edit to id_rsa still
    fires (protected .ssh dir if under one, or root-escape), but NOT via the credential-basename
    family specifically; here we use a cwd-relative bare basename with no protected dir ancestor to
    isolate the family and confirm Edit doesn't trip credential-basename (it may still be clean)."""
    _clean(_edit("id_rsa", cwd="/repo"))


def test_notebookedit_protected_dir_GAP_fix():
    """CONFIRMED-BUG regression: NotebookEdit must be judged too."""
    assert "protected-directory" in _reason(_notebookedit("/root/.aws/nb.ipynb"))


# --- makoto's own resolved STATE-HOME (dynamic; PENDING item this port resolves) ------------------

def test_denies_write_under_resolved_state_home(monkeypatch, tmp_path):
    state_home = tmp_path / "custom_makoto_state"
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(state_home))
    target = str(state_home / "db.sqlite3")
    assert "makoto-state-home" in _reason(_write(target))


# --- root-escape -----------------------------------------------------------------------------------

def test_denies_root_escape_relative_path():
    assert "root-escape" in _reason(_write("../outside.py", cwd="/repo/project"))


def test_clean_write_within_cwd():
    _clean(_write("src/module.py", cwd="/repo/project"))


def test_undecidable_relative_no_cwd_is_silent():
    """a relative path with no cwd is never guessed -- silent, not a false fire."""
    _clean(_write("some/relative/path.py"))


# --- gating: non-PreToolUse / non-monitored tool ---------------------------------------------------

def test_silent_on_non_pretooluse_event():
    evt = _write("/root/.ssh/id_rsa")
    evt["hook_event_name"] = "Stop"
    _clean(evt)


def test_silent_on_non_monitored_tool():
    _clean(_evt("Bash", {"command": "cat /root/.ssh/id_rsa"}))


def test_silent_on_missing_location_arg():
    _clean(_evt("Write", {"content": "x"}))


# --- harness-designated plan directory (root-escape carve-out; guards keep protection) --------------

def _home_claude(*parts):
    from pathlib import Path
    return str(Path.home().joinpath(".claude", *parts))


def test_harness_plan_dir_is_designated_writable():
    """The host harness's plan mode designates <home>/.claude/plans as THE plan-artifact home --
    a write there is harness-sanctioned, not a root-escape (live FP: this exact fire blocked a
    plan-mode file three times on 2026-07-07)."""
    _clean(_write(_home_claude("plans", "my-plan.md"), cwd="/home/user"))


def test_harness_plan_dir_edit_is_designated_writable_too():
    _clean(_edit(_home_claude("plans", "my-plan.md"), cwd="/home/user"))


def test_non_plans_claude_path_still_root_escapes():
    """narrowness: the carve-out is plans/ EXACTLY -- a sibling .claude subdir outside cwd still
    fires root-escape."""
    assert "root-escape" in _reason(_write(_home_claude("other", "x.md"), cwd="/home/user"))


def test_makoto_control_plane_under_claude_still_protected():
    """ordering: the control-plane guard runs BEFORE the plans carve-out could ever be consulted --
    settings.json keeps its protection unconditionally."""
    assert "makoto-control-plane" in _reason(_write(_home_claude("settings.json"), cwd="/home/user"))


def test_makoto_state_home_under_claude_still_protected(monkeypatch):
    """ordering: makoto's own state dir keeps its protection even though it lives under .claude."""
    assert "makoto-state-home" in _reason(_write(_home_claude("makoto_state", "audit.jsonl"),
                                                  cwd="/home/user"))


def test_plans_lookalike_outside_home_still_root_escapes():
    """narrowness: a 'plans' segment elsewhere is NOT the harness plan dir."""
    assert "root-escape" in _reason(_write("/srv/other/.claude/plans/x.md", cwd="/home/user"))
