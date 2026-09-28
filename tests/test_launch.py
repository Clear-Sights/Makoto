"""The launch checklist: START's launch line stays cheap, and the installed-copy line names the copy
whose hooks run. Each test reads a fixture home (conftest gives every test its own HOME)."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("makoto_copies", REPO / "tools" / "makoto_copies.py")
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)


def launch_lines(text: str) -> list[str]:
    return re.findall(r"^Run `sh tools/launch_check\.sh[^`]*`.*$", text, re.M)


def test_start_launches_without_the_suite():
    """The suite re-runs what main's merge already ran (76 s of 85): START's launch line never
    brings `--suite` back; it belongs before a step is called done."""
    lines = launch_lines((REPO / "START.md").read_text(encoding="utf-8"))
    assert len(lines) == 1, lines
    assert "--suite" not in lines[0], lines[0]


def test_the_launch_line_check_reads_red_on_its_plant():
    planted = "## Launch checklist\n\nRun `sh tools/launch_check.sh --suite` before anything else.\n"
    (line,) = launch_lines(planted)
    assert "--suite" in line


def _copy(path: Path, version: str) -> Path:
    (path / ".claude-plugin").mkdir(parents=True)
    (path / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "makoto", "version": version}))
    return path


def _states(home: Path) -> dict[str, tuple[str, str]]:
    return {p.relative_to(home / ".claude" / "plugins").as_posix(): (state, ver) for state, p, ver, _ in mc.copies(home)}


def test_the_synced_generation_the_manifest_lists_is_live_and_the_rest_unused(tmp_path):
    org = tmp_path / ".claude" / "plugins" / "synced" / "org"
    _copy(org / "makoto~g2", "3.4.5")
    _copy(org / "makoto", "3.1.0")
    (org / "manifest.json").write_text(json.dumps({"plugins": [{"name": "makoto", "generation": 2}]}))
    assert _states(tmp_path) == {"synced/org/makoto~g2": ("live", "3.4.5"),
                                 "synced/org/makoto": ("unused", "3.1.0")}


def test_a_synced_copy_the_manifest_does_not_list_is_unused(tmp_path):
    org = tmp_path / ".claude" / "plugins" / "synced" / "org"
    _copy(org / "makoto", "3.4.5")
    (org / "manifest.json").write_text(json.dumps({"plugins": [{"name": "codex"}]}))
    assert _states(tmp_path) == {"synced/org/makoto": ("unused", "3.4.5")}


def test_a_marketplace_copy_is_live_only_when_enabled_at_its_recorded_path(tmp_path):
    cache = tmp_path / ".claude" / "plugins" / "cache" / "Makoto" / "makoto"
    old, new = _copy(cache / "2.8.5", "2.8.5"), _copy(cache / "3.4.6", "3.4.6")
    assert _states(tmp_path) == {"cache/Makoto/makoto/2.8.5": ("unused", "2.8.5"),
                                 "cache/Makoto/makoto/3.4.6": ("unused", "3.4.6")}
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"makoto@Makoto": True}}))
    (tmp_path / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"makoto@Makoto": [{"installPath": str(old), "version": "2.8.5"}]}}))
    assert _states(tmp_path) == {"cache/Makoto/makoto/2.8.5": ("live", "2.8.5"),
                                 "cache/Makoto/makoto/3.4.6": ("unused", "3.4.6")}
    (tmp_path / ".claude" / "plugins" / "installed_plugins.json").unlink()
    assert _states(tmp_path)["cache/Makoto/makoto/3.4.6"] == ("live", "3.4.6")
    assert new.is_dir()


def test_no_install_names_no_copy(tmp_path):
    assert mc.copies(tmp_path) == []


def test_a_synced_copy_and_an_enabled_marketplace_copy_are_both_live(tmp_path):
    """The case session.sh can create (it installs makoto@makoto beside an account-synced copy):
    both load, so every hook runs twice, and launch must say which one to keep."""
    org = tmp_path / ".claude" / "plugins" / "synced" / "org"
    _copy(org / "makoto~g2", "3.4.5")
    (org / "manifest.json").write_text(json.dumps({"plugins": [{"name": "makoto", "generation": 2}]}))
    _copy(tmp_path / ".claude" / "plugins" / "cache" / "makoto" / "makoto" / "3.4.6", "3.4.6")
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"makoto@makoto": True}}))
    assert _states(tmp_path) == {"synced/org/makoto~g2": ("live", "3.4.5"),
                                 "cache/makoto/makoto/3.4.6": ("live", "3.4.6")}
