"""tests for install lifecycle — settings.json wiring, install gates.

1.0.3 collapse: cmd_init removed (vestigial post-5.4 — lazy init covers it).
cmd_install now does state-dir setup AND settings.json wiring in one call.
"""
import json
import pytest
from pathlib import Path
from makoto.install import (
    _wire_claude_hooks,
    _unwire_claude_hooks,
    cmd_install,
    cmd_uninstall,
)


def test_wire_claude_hooks_adds_managed_section(tmp_path):
    """wire adds Makoto-managed PreToolUse + Stop entries to settings.json."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    _wire_claude_hooks(settings_path)
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"  # preserved
    assert "hooks" in data
    assert any(h.get("_makoto_managed") for h in data["hooks"].get("PreToolUse", []))
    assert any(h.get("_makoto_managed") for h in data["hooks"].get("Stop", []))


def test_wire_claude_hooks_idempotent(tmp_path):
    """wiring twice produces the same settings.json as wiring once."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    _wire_claude_hooks(settings_path)
    after_one = settings_path.read_text(encoding="utf-8")
    _wire_claude_hooks(settings_path)
    after_two = settings_path.read_text(encoding="utf-8")
    assert after_one == after_two


def test_wire_claude_hooks_absorbs_hand_wired_entry(tmp_path):
    """wire must not double-dispatch a device that is already FUNCTIONALLY wired.

    A hand-wired / shim entry (no `_makoto_managed` flag, command pointing at makoto's
    dispatch) is the same install state v1.2.1 taught `_hooks_wired` to recognize. The
    wirer must apply the same functional truth: absorb such entries into the single
    managed entry instead of appending a duplicate — caught live on 2026-06-10, when
    `makoto install` on a shim-wired device produced two dispatch.sh fires per event.
    """
    settings_path = tmp_path / "settings.json"
    shim = str(tmp_path / "makoto_state" / "dispatch.sh")
    settings_path.write_text(json.dumps({"hooks": {
        "PreToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": shim}]},
            {"matcher": "*", "hooks": [{"type": "command", "command": "other-tool --check"}]},
        ],
        "PostToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "python -m makoto._dispatch"}]}],
        "Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": shim}]}],
    }}), encoding="utf-8")
    _wire_claude_hooks(settings_path)
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    for evt in ("PreToolUse", "PostToolUse", "Stop"):
        makoto_entries = [h for h in data["hooks"][evt]
                          if "makoto" in json.dumps(h).lower()]
        assert len(makoto_entries) == 1, f"{evt}: double-dispatch ({len(makoto_entries)} entries)"
        assert makoto_entries[0].get("_makoto_managed") is True
    other = [h for h in data["hooks"]["PreToolUse"] if "other-tool" in json.dumps(h)]
    assert len(other) == 1  # user's non-makoto hook preserved
    before = settings_path.read_text(encoding="utf-8")
    _wire_claude_hooks(settings_path)
    assert settings_path.read_text(encoding="utf-8") == before  # idempotent after absorption


def test_unwire_claude_hooks_removes_managed_section(tmp_path):
    """unwire removes Makoto-managed entries; non-Makoto entries preserved."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    _wire_claude_hooks(settings_path)
    _unwire_claude_hooks(settings_path)
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    for evt in ("PreToolUse", "Stop"):
        for h in data.get("hooks", {}).get(evt, []):
            assert not h.get("_makoto_managed")


def test_unwire_is_idempotent(tmp_path):
    """unwire on a clean file does nothing (no crash)."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    _unwire_claude_hooks(settings_path)
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"


def test_cmd_install_creates_state_dir_db_and_wires_settings(tmp_path, monkeypatch):
    """cmd_install creates state dir + makoto.record.db + wires settings.json (one command)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    rc = cmd_install()
    assert rc == 0
    state_dir = fake_home / ".claude" / "makoto_state"
    assert state_dir.is_dir()
    assert (state_dir / "makoto.record.db").is_file()
    settings = fake_home / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text())
    found = False
    for ev in ("PreToolUse", "Stop"):
        for h in data.get("hooks", {}).get(ev, []):
            if h.get("_makoto_managed"):
                found = True
    assert found, "cmd_install must wire settings.json"


def test_cmd_install_records_configchange_manifest(tmp_path, monkeypatch):
    """D5 (docs/DEFERRED.md, owner-authorized 2026-07-08): cmd_install records the settings path
    it wires into <state_dir>/configchange_manifest.json, so _dispatch_configchange.py's blocking
    tier can later treat a full-strip of THIS exact path as a genuine strip, not the ambiguous
    never-wired case."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    rc = cmd_install()
    assert rc == 0
    manifest_path = fake_home / ".claude" / "makoto_state" / "configchange_manifest.json"
    assert manifest_path.exists()
    paths = json.loads(manifest_path.read_text())
    settings = fake_home / ".claude" / "settings.json"
    assert str(settings.resolve()) in paths


def test_cmd_install_idempotent(tmp_path, monkeypatch):
    """re-running cmd_install does not crash and produces identical settings.json."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    cmd_install()
    settings = fake_home / ".claude" / "settings.json"
    after_one = settings.read_text()
    cmd_install()
    assert settings.read_text() == after_one


def test_cmd_uninstall_reverses_install(tmp_path, monkeypatch):
    """cmd_uninstall removes makoto-managed hook entries from settings.json."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    settings_path = fake_home / ".claude" / "settings.json"
    settings_path.write_text('{"theme": "dark"}\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    _wire_claude_hooks(settings_path)
    data = json.loads(settings_path.read_text())
    assert "hooks" in data
    cmd_uninstall()
    assert json.loads(settings_path.read_text()) == {"theme": "dark"}


def test_validate_predicate_modules_passes_on_current_catalog():
    """the live checks/ catalog (SPEC-C item 2 Pre-tier cutover -- no longer literally
    patterns.toml): validation gate passes, i.e. it does NOT sys.exit(1) against the real,
    current predicate modules."""
    from makoto.install import _validate_predicate_modules
    try:
        _validate_predicate_modules()
        raised = False
    except SystemExit:
        raised = True
    assert not raised, "validation gate must pass (not sys.exit) against the current live catalog"


def test_validate_predicate_modules_aborts_on_missing_callable(monkeypatch, capsys):
    """if a pattern's predicate_module has no 'predicate' callable, abort install."""
    import sys, types
    broken_mod = types.ModuleType("makoto.prechecks.precheck_broken")
    monkeypatch.setitem(sys.modules, "makoto.prechecks.precheck_broken", broken_mod)
    from makoto.core.schema import PreCheck
    fake_patterns = [
        PreCheck(id="x", fire_level="error", description="d",
                predicate_module="makoto.prechecks.precheck_broken",
                keywords=["x"]),
    ]
    import makoto.install as install_mod
    monkeypatch.setattr(install_mod, "load_prechecks", lambda *a, **kw: fake_patterns)
    with pytest.raises(SystemExit) as excinfo:
        install_mod._validate_predicate_modules()
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "predicate" in captured.err.lower()


def test_install_conventions_writes_block_idempotent_preserves_user_content(tmp_path):
    """_install_claude_conventions writes the makoto-allow conventions block, preserves user
    content, is idempotent (exactly one block on repeat), and uninstall removes it cleanly."""
    from makoto.install import (_install_claude_conventions, _uninstall_claude_conventions,
                                _CONV_START)
    cm = tmp_path / "CLAUDE.md"
    cm.write_text("# My prefs\n\nUser content I care about.\n", encoding="utf-8")
    _install_claude_conventions(cm)
    t1 = cm.read_text(encoding="utf-8")
    assert "User content I care about." in t1, "must preserve user content"
    assert "makoto-allow" in t1, "must teach the makoto-allow convention"
    assert "monoton" in t1.lower(), "conventions must teach the monotonicity invariant"
    assert "bypassable test was never a test" in t1, "conventions must state the monotonicity maxim"
    _install_claude_conventions(cm)  # idempotent
    t2 = cm.read_text(encoding="utf-8")
    assert t2.count(_CONV_START) == 1, "re-install must not duplicate the block"
    assert t1 == t2, "re-install must be a no-op"
    _uninstall_claude_conventions(cm)
    t3 = cm.read_text(encoding="utf-8")
    assert _CONV_START not in t3 and "User content I care about." in t3, "uninstall removes block, keeps user content"


def test_install_conventions_creates_file_when_absent(tmp_path):
    from makoto.install import _install_claude_conventions, _CONV_START
    cm = tmp_path / "nested" / "CLAUDE.md"  # parent dir absent
    _install_claude_conventions(cm)
    assert cm.exists() and _CONV_START in cm.read_text(encoding="utf-8")


def test_cmd_status_reports_no_chain_file_key(tmp_path, monkeypatch, capsys):
    """status output carries no last_chain_files key — the chain_*.log class has no
    in-repo writer, so the key was permanently [] (io-purge B2 removed the dead read)."""
    from makoto.install import cmd_status
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert cmd_status() == 0
    status = json.loads(capsys.readouterr().out)
    assert "last_chain_files" not in status
