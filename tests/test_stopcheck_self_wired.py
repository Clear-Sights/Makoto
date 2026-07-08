"""gate.self_wired — advisory-only partial-strip detection of makoto's own .claude/settings.json
hook wiring. Fires iff PreToolUse/PostToolUse/Stop is missing a makoto-dispatching entry while the
file otherwise parses; never blocks (level='advisory', not 'error'). Documented blind spot: a
single edit that strips ALL THREE simultaneously disables this check in the same instant it would
have fired (Claude Code reloads hooks.json live, not once at session start), so it provides ZERO
coverage against that canonical full-strip attack — see docs/self-defense-asymmetry-followup.md.
"""
import json

from makoto.checks.selfWiredCheck import (
    GATE,
    _entry_dispatches_to_makoto,
    _missing_makoto_events,
    self_wired_gate,
)


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


def test_gate_export_shape():
    assert GATE.id == "gate.self_wired"
    assert GATE.fn is self_wired_gate


def test_gate_run_adapter_reads_relative_settings_path():
    seen = {}

    def fs_read(path):
        seen["path"] = path
        return _settings()

    ctx = type("Ctx", (), {"fs_read": staticmethod(fs_read)})()
    assert GATE.run(ctx) is None
    assert seen["path"] == ".claude/settings.json"
