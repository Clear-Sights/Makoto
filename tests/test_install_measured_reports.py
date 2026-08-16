"""#20 (uninstall reports false success) -- every install/uninstall/status report field is
MEASURED (a post-condition re-read from disk), never asserted, and removal keys on the SAME
functional predicate reporting uses (`wiring.entry_owned_by_makoto`), so install and uninstall
are inverses and uninstall/status can no longer contradict each other.

The original defect: `_unwire_claude_hooks` keyed on the `_makoto_managed` flag ALONE. Claude
Code re-serializes settings.json from a schema-parsed representation that drops unknown keys --
including `_makoto_managed` -- while KEEPING the hook entries. After one such rewrite the filter
matched nothing: uninstall removed zero entries, forever, while printing
`{"unwired": true, ...}` -- and `makoto status`, run immediately after, printed
`hooks_wired: true`.

Reproduction discipline: `test_uninstall_removes_decayed_flagless_entries_and_reports_measured`
and `test_uninstall_and_status_agree_after_flag_decay` were run against the unfixed tree and
failed exactly on the reported defect (unwired claimed True while the functional entries
remained), then passed with the fix.
"""
import json
from pathlib import Path

import pytest

from makoto import install as inst


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("MAKOTO_DISABLE_PATTERNS", raising=False)
    return home


def _decayed_settings(home) -> Path:
    """settings.json as Claude Code re-serializes it: makoto's functional hook entries kept,
    the `_makoto_managed` flags dropped. Plus one user entry that must survive uninstall."""
    settings = home / ".claude" / "settings.json"
    dispatch = str(home / ".claude" / "makoto_state" / "dispatch.sh")
    entry = {"matcher": "*", "hooks": [{"type": "command", "command": dispatch}]}
    user = {"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto.status"}]}
    settings.write_text(json.dumps({
        "theme": "dark",
        "hooks": {"PreToolUse": [entry, user], "PostToolUse": [entry], "Stop": [entry]},
    }, indent=2) + "\n", encoding="utf-8")
    return settings


def test_uninstall_removes_decayed_flagless_entries_and_reports_measured(fake_home, capsys):
    settings = _decayed_settings(fake_home)
    assert inst.cmd_uninstall() == 0
    report = json.loads(capsys.readouterr().out)
    data = json.loads(settings.read_text(encoding="utf-8"))
    # THE #20 reproduction: the three decayed functional entries must actually be gone...
    for evt in ("PreToolUse", "PostToolUse", "Stop"):
        assert not any(inst._entry_dispatches_to_makoto(h)
                       for h in data.get("hooks", {}).get(evt, [])), evt
    # ...and the report must agree with the measured world.
    assert report["hook_entries_removed"] == 3
    assert report["unwired"] is True
    # the user's own makoto-CLI hook survives (the security fix's ownership bound)
    assert any("makoto.status" in json.dumps(h)
               for h in data.get("hooks", {}).get("PreToolUse", []))


def test_uninstall_and_status_agree_after_flag_decay(fake_home, capsys):
    """uninstall's `unwired` and status's `hooks_wired` are the same measured predicate."""
    _decayed_settings(fake_home)
    assert inst.cmd_uninstall() == 0
    unwired = json.loads(capsys.readouterr().out)["unwired"]
    assert inst.cmd_status() == 0
    hooks_wired = json.loads(capsys.readouterr().out)["hooks_wired"]
    assert unwired == (not hooks_wired) == True  # noqa: E712  -- the exact reported contradiction


def test_uninstall_reports_nothing_removed_when_nothing_was(fake_home, capsys):
    settings = fake_home / ".claude" / "settings.json"
    settings.write_text('{"theme": "dark"}\n', encoding="utf-8")
    assert inst.cmd_uninstall() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["hook_entries_removed"] == 0
    assert report["conventions_removed"] is False   # no CLAUDE.md block existed to strip
    assert report["unwired"] is True


def test_install_reports_are_postconditions(fake_home, capsys):
    assert inst.cmd_install() == 0
    report = json.loads(capsys.readouterr().out)
    state_dir = fake_home / ".claude" / "makoto_state"
    assert report["state_dir_present"] is True and state_dir.is_dir()
    assert report["dispatch_shim_installed"] == (state_dir / "dispatch.sh").exists()
    assert report["makoto_db_initialized"] == (state_dir / "makoto.record.db").exists()
    assert report["settings_wired"] is True
    assert report["conventions_written"] is True
    # and install -> uninstall is an inverse round-trip on the hooks
    assert inst.cmd_uninstall() == 0
    report2 = json.loads(capsys.readouterr().out)
    assert report2["unwired"] is True and report2["hook_entries_removed"] == 3


def test_install_absorbs_hand_wired_dispatch_but_not_user_cli(fake_home, capsys):
    settings = fake_home / ".claude" / "settings.json"
    hand = {"matcher": "*", "hooks": [{"type": "command",
                                       "command": "python3 -m makoto.dispatch"}]}
    user = {"matcher": "*", "hooks": [{"type": "command",
                                       "command": "python3 -m makoto.reference_integrity"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [hand, user]}}) + "\n",
                        encoding="utf-8")
    assert inst.cmd_install() == 0
    capsys.readouterr()
    data = json.loads(settings.read_text(encoding="utf-8"))
    pre = data["hooks"]["PreToolUse"]
    assert sum(1 for h in pre if inst._entry_dispatches_to_makoto(h)) == 1  # absorbed, once
    assert any("reference_integrity" in json.dumps(h) for h in pre)         # user hook kept


def test_status_separates_requested_vs_effective_mutes(fake_home, capsys, monkeypatch):
    """8fec86e's status fix: an id registered on the Stop edge too (gate.contract_order) cannot
    be fully muted by MAKOTO_DISABLE_PATTERNS (the Stop half never consults it) -- status must
    say so instead of claiming a complete mute."""
    monkeypatch.setenv("MAKOTO_DISABLE_PATTERNS",
                       "gate.contract_order,content.self_mute_guard")
    assert inst.cmd_status() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["patterns_disable_requested"] == ["gate.contract_order",
                                                    "content.self_mute_guard"]
    assert "gate.contract_order" in report["patterns_disable_ineffective"]
    assert report["patterns_disabled"] == ["content.self_mute_guard"]
