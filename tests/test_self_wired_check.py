"""gate.self_wired — advisory-only partial-strip detection of makoto's own hook wiring, checked
across BOTH `.claude/settings.json` and (2026-07-22) the plugin's own hooks/hooks.json manifest.
Fires iff PreToolUse/PostToolUse/Stop is missing a makoto-dispatching entry from NEITHER source
while settings.json otherwise parses; never blocks (level='advisory', not 'error'). Documented
blind spot: an edit that strips ALL THREE from BOTH sources simultaneously disables this check in
the same instant it would have fired for the settings.json-only case (Claude Code reloads
hooks.json live, not once at session start), so it provides ZERO coverage against that canonical
full-strip attack — see docs/self-defense-asymmetry-followup.md.
"""
import json

from makoto.checks.selfWiredCheck import (
    CHECK,
    _entry_dispatches_to_makoto,
    _missing_makoto_events,
    self_wired_gate,
)
from makoto.substrate.wiring import event_wired, read_plugin_manifest_hooks


def _settings(pre=True, post=True, stop=True):
    def _entry(wired):
        hooks = [{"type": "command", "command": "python3 -m makoto._dispatch"}] if wired \
            else [{"type": "command", "command": "python3 -m ventura.adapters.hook_bridge"}]
        return {"matcher": "*", "hooks": hooks}

    return json.dumps({"hooks": {
        "PreToolUse": [_entry(pre)],
        "PostToolUse": [_entry(post)],
        "Stop": [_entry(stop)],
    }})


def _reader(text):
    return lambda path: text


def test_all_three_wired_no_finding():
    assert self_wired_gate(_reader(_settings())) is None


def test_one_event_missing_fires_advisory_naming_it():
    f = self_wired_gate(_reader(_settings(stop=False)))
    assert f is not None
    assert f.pattern_id == "gate.self_wired"
    assert f.level == "advisory"          # never "error" — advisory over blocking (condition c)
    assert "Stop" in f.message
    assert "PreToolUse" not in f.message and "PostToolUse" not in f.message


def test_managed_flag_entry_also_counts_as_wired():
    settings = json.dumps({"hooks": {
        "PreToolUse": [{"_makoto_managed": True, "matcher": "*",
                         "hooks": [{"type": "command", "command": "/home/u/.claude/makoto_state/dispatch.sh"}]}],
        "PostToolUse": [{"_makoto_managed": True, "matcher": "*",
                          "hooks": [{"type": "command", "command": "/home/u/.claude/makoto_state/dispatch.sh"}]}],
        "Stop": [{"_makoto_managed": True, "matcher": "*",
                  "hooks": [{"type": "command", "command": "/home/u/.claude/makoto_state/dispatch.sh"}]}],
    }})
    assert self_wired_gate(_reader(settings)) is None


def test_malformed_json_fails_open():
    assert self_wired_gate(_reader("{not valid json")) is None


def test_missing_file_fails_open():
    assert self_wired_gate(lambda path: None) is None


def test_empty_string_fails_open():
    assert self_wired_gate(_reader("")) is None


def test_non_dict_json_fails_open():
    assert self_wired_gate(_reader("[1, 2, 3]")) is None


def test_hooks_key_not_a_dict_fails_open_to_missing_all():
    # "hooks" present but the wrong shape: treated as no wiring at all (fires, does not crash).
    f = self_wired_gate(_reader(json.dumps({"hooks": "not-a-dict"})))
    assert f is not None
    assert "PreToolUse" in f.message and "PostToolUse" in f.message and "Stop" in f.message


def test_fs_read_raising_fails_open():
    def _boom(path):
        raise OSError("permission denied")
    assert self_wired_gate(_boom) is None


def test_no_fs_read_fails_open():
    assert self_wired_gate(None) is None


def test_all_three_missing_predicate_reports_all_three():
    # Exercises the predicate function DIRECTLY (not the live hook chain). In real usage, a single
    # edit that strips all three of makoto's PreToolUse/PostToolUse/Stop entries simultaneously
    # also strips the Stop entry that would run gate.self_wired itself — so this exact scenario
    # never actually gets checked in-session (documented blind spot, module docstring). This test
    # only pins that _missing_makoto_events's logic is correct in isolation, not that the live
    # hook chain would ever observe it for a real full strip.
    hooks = {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "other-tool"}]}],
        "PostToolUse": [],
        "Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "ventura.hook_bridge"}]}],
    }
    assert _missing_makoto_events(hooks) == ["PreToolUse", "PostToolUse", "Stop"]


def test_entry_dispatches_to_makoto_matches_install_semantics():
    assert _entry_dispatches_to_makoto({"_makoto_managed": True}) is True
    assert _entry_dispatches_to_makoto(
        {"hooks": [{"type": "command", "command": "python3 -m makoto._dispatch"}]}) is True
    assert _entry_dispatches_to_makoto(
        {"hooks": [{"type": "command", "command": "python3 -m ventura.adapters.hook_bridge"}]}) is False
    assert _entry_dispatches_to_makoto("not-a-dict") is False


def test_check_export_shape():
    assert CHECK.id == "gate.self_wired"
    assert CHECK.applies_at == "Stop"
    assert CHECK.posture == "ADVISE"


def test_check_run_adapter_delegates_to_self_wired_gate():
    # No separate `.fn` attribute anymore (GATE/StopCheck retired) -- prove delegation
    # behaviorally: CHECK.run(ctx) must produce exactly what self_wired_gate(ctx.fs_read) does.
    ctx = type("Ctx", (), {"fs_read": staticmethod(_reader(_settings(stop=False)))})()
    assert CHECK.run(ctx) == self_wired_gate(ctx.fs_read)


def test_gate_run_adapter_reads_relative_settings_path():
    seen = {}

    def fs_read(path):
        seen["path"] = path
        return _settings()

    ctx = type("Ctx", (), {"fs_read": staticmethod(fs_read)})()
    assert CHECK.run(ctx) is None
    assert seen["path"] == ".claude/settings.json"


# --- Two-source wiring (2026-07-22): the plugin's own hooks/hooks.json manifest counts as an ----
# equally-valid wiring source alongside settings.json's own "hooks" key, for a plugin-packaged
# install where settings.json legitimately never duplicates the plugin manifest's own entries.

def _plugin_manifest(pre=True, post=True, stop=True):
    def _entry(wired):
        hooks = [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh"}] \
            if wired else [{"type": "command", "command": "some-other-tool"}]
        return {"matcher": "*", "hooks": hooks}

    return json.dumps({"hooks": {
        "PreToolUse": [_entry(pre)],
        "PostToolUse": [_entry(post)],
        "Stop": [_entry(stop)],
    }})


def test_plugin_manifest_covers_a_settings_json_missing_event():
    # settings.json alone is missing Stop; the plugin manifest wires it -> no finding at all.
    f = self_wired_gate(_reader(_settings(stop=False)), plugin_root="/fake/plugin/root",
                         plugin_fs_read=_reader(_plugin_manifest(stop=True)))
    assert f is None


def test_plugin_manifest_also_missing_the_event_still_fires():
    # A genuine partial strip: missing from settings.json AND the plugin manifest doesn't cover
    # it either -> still fires, still names exactly the missing event. This is the required
    # invariant: broadening the check to a second source must never let a REAL strip go silent.
    f = self_wired_gate(_reader(_settings(stop=False)), plugin_root="/fake/plugin/root",
                         plugin_fs_read=_reader(_plugin_manifest(stop=False)))
    assert f is not None
    assert "Stop" in f.message
    assert f.level == "advisory"


def test_all_events_wired_by_plugin_manifest_alone_no_finding():
    # The real-world case this fix targets: a fresh/never-configured settings.json (no "hooks"
    # key at all) with every event actually wired via the plugin manifest instead.
    f = self_wired_gate(_reader(json.dumps({})), plugin_root="/fake/plugin/root",
                         plugin_fs_read=_reader(_plugin_manifest()))
    assert f is None


def test_no_plugin_root_matches_prior_settings_only_behavior():
    # plugin_root explicitly absent (no env, no override) -> behaves exactly as before this fix:
    # a settings.json gap is reported, full stop, no regression for the no-plugin-manifest case.
    f = self_wired_gate(_reader(_settings(stop=False)), plugin_root=None, plugin_fs_read=_reader(_plugin_manifest()))
    assert f is not None
    assert "Stop" in f.message


def test_plugin_manifest_unreadable_fails_closed_still_fires():
    def _boom(path):
        raise OSError("permission denied")
    f = self_wired_gate(_reader(_settings(stop=False)), plugin_root="/fake/plugin/root", plugin_fs_read=_boom)
    assert f is not None
    assert "Stop" in f.message


def test_plugin_manifest_malformed_json_fails_closed_still_fires():
    f = self_wired_gate(_reader(_settings(stop=False)), plugin_root="/fake/plugin/root",
                         plugin_fs_read=_reader("{not valid json"))
    assert f is not None
    assert "Stop" in f.message


def test_plugin_manifest_missing_file_fails_closed_still_fires():
    f = self_wired_gate(_reader(_settings(stop=False)), plugin_root="/fake/plugin/root",
                         plugin_fs_read=lambda path: None)
    assert f is not None
    assert "Stop" in f.message


def test_plugin_manifest_path_is_root_relative_hooks_hooks_json():
    seen = {}

    def _read(path):
        seen["path"] = path
        return _plugin_manifest()

    f = self_wired_gate(_reader(_settings(stop=False)), plugin_root="/fake/plugin/root", plugin_fs_read=_read)
    assert f is None
    assert seen["path"].replace("\\", "/") == "/fake/plugin/root/hooks/hooks.json"


def test_missing_makoto_events_direct_two_source():
    settings_hooks = {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": "python3 -m makoto._dispatch"}]}]}   # only PreToolUse wired
    plugin_hooks_json = _plugin_manifest(pre=False, post=True, stop=False)   # only PostToolUse wired
    missing = _missing_makoto_events(settings_hooks, plugin_root="/fake/plugin/root",
                                      plugin_fs_read=_reader(plugin_hooks_json))
    assert missing == ["Stop"]   # PreToolUse via settings, PostToolUse via plugin, Stop by neither


def test_event_wired_helper_matches_entry_dispatches_semantics():
    hooks = {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 -m makoto._dispatch"}]}]}
    assert event_wired(hooks, "Stop") is True
    assert event_wired(hooks, "PreToolUse") is False
    assert event_wired("not-a-dict", "Stop") is False


def test_read_plugin_manifest_hooks_helper_fails_closed():
    assert read_plugin_manifest_hooks(None, _reader(_plugin_manifest())) == {}
    assert read_plugin_manifest_hooks("/root", lambda p: None) == {}
    assert read_plugin_manifest_hooks("/root", _reader("{not valid")) == {}
    assert read_plugin_manifest_hooks("/root", _reader(json.dumps({"hooks": "not-a-dict"}))) == {}
    got = read_plugin_manifest_hooks("/root", _reader(_plugin_manifest()))
    assert isinstance(got, dict) and "Stop" in got
