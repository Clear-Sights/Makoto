"""Tests for `makoto.configchange_verdict` — a pure predicate, not a live hook (see module
docstring for why: this is detection logic for a hypothetical future `ConfigChange` hook adapter
that has NOT been wired into `.claude/settings.json`, per CLAUDE.md rule 4 this repo's dispatchers
may not do that unilaterally). Every test below constructs a fake ConfigChange-shaped payload; none
of them exercises a real Claude Code hook event, because no such live event stream exists to test
against yet.
"""
from __future__ import annotations
import json

from makoto.configchange_verdict import ConfigChangeVerdict, configchange_verdict


def _settings(pre=True, post=True, stop=True):
    def _entry(wired):
        hooks = [{"type": "command", "command": "python3 -m makoto._dispatch"}] if wired \
            else [{"type": "command", "command": "python3 -m ventura.adapters.hook_bridge"}]
        return {"matcher": "*", "hooks": hooks}

    return {"hooks": {
        "PreToolUse": [_entry(pre)],
        "PostToolUse": [_entry(post)],
        "Stop": [_entry(stop)],
    }}


def _event(config_source="project_settings", config_path=".claude/settings.json"):
    return {"config_source": config_source, "config_path": config_path}


# --- applicable + fully wired: clean ------------------------------------------------------------
def test_clean_project_settings_all_wired_does_not_fire():
    v = configchange_verdict(_event(), settings_json=_settings())
    assert isinstance(v, ConfigChangeVerdict)
    assert v.applicable is True
    assert v.evaluated is True
    assert v.stripped is False
    assert v.missing_events == ()
    assert v.fires is False


def test_local_settings_source_is_also_applicable():
    v = configchange_verdict(_event(config_source="local_settings",
                                     config_path=".claude/settings.local.json"),
                              settings_json=_settings())
    assert v.applicable is True
    assert v.fires is False


# --- partial strip: fires, names exactly what's missing -----------------------------------------
def test_partial_strip_of_one_event_fires():
    v = configchange_verdict(_event(), settings_json=_settings(stop=False))
    assert v.applicable is True
    assert v.evaluated is True
    assert v.stripped is True
    assert v.missing_events == ("Stop",)
    assert v.fires is True
    assert "Stop" in v.reason


# --- full simultaneous strip: fires -- the whole point (unlike gate.self_wired's Stop-time blind
# spot, a PRE-change ConfigChange check can see a full strip about to happen, because it is
# triggered by Claude Code's file-watcher independent of Makoto's own Stop hook being one of the
# things stripped) ---------------------------------------------------------------------------------
def test_full_simultaneous_strip_of_all_three_fires():
    v = configchange_verdict(_event(), settings_json=_settings(pre=False, post=False, stop=False))
    assert v.applicable is True
    assert v.evaluated is True
    assert v.stripped is True
    assert set(v.missing_events) == {"PreToolUse", "PostToolUse", "Stop"}
    assert v.fires is True


# --- unrelated config_source: never applicable, regardless of how stripped the content is -------
def test_unrelated_config_source_user_settings_not_applicable():
    stripped_content = _settings(pre=False, post=False, stop=False)
    v = configchange_verdict(_event(config_source="user_settings", config_path="~/.claude/settings.json"),
                              settings_json=stripped_content)
    assert v.applicable is False
    assert v.evaluated is False
    assert v.fires is False
    assert v.missing_events == ()


def test_unrelated_config_source_policy_settings_not_applicable():
    v = configchange_verdict(_event(config_source="policy_settings", config_path="/etc/claude/policy.json"),
                              settings_json=_settings(pre=False, post=False, stop=False))
    assert v.applicable is False
    assert v.fires is False


def test_unrelated_config_source_skills_not_applicable():
    v = configchange_verdict(_event(config_source="skills", config_path=".claude/skills/foo.md"))
    assert v.applicable is False
    assert v.fires is False


def test_missing_config_source_key_treated_as_not_applicable():
    v = configchange_verdict({"config_path": ".claude/settings.json"})
    assert v.applicable is False
    assert v.fires is False


# --- content-unavailable edge cases: fail open, never fire ---------------------------------------
def test_no_settings_content_source_at_all_fails_open():
    v = configchange_verdict(_event())
    assert v.applicable is True
    assert v.evaluated is False
    assert v.fires is False


def test_fs_read_returning_none_fails_open():
    v = configchange_verdict(_event(), fs_read=lambda path: None)
    assert v.evaluated is False
    assert v.fires is False


def test_fs_read_raising_fails_open():
    def _boom(path):
        raise OSError("permission denied")
    v = configchange_verdict(_event(), fs_read=_boom)
    assert v.evaluated is False
    assert v.fires is False


def test_malformed_json_from_fs_read_fails_open():
    v = configchange_verdict(_event(), fs_read=lambda path: "{not valid json")
    assert v.evaluated is False
    assert v.fires is False


def test_non_dict_settings_json_fails_open():
    v = configchange_verdict(_event(), settings_json=[1, 2, 3])
    assert v.evaluated is False
    assert v.fires is False


def test_hooks_key_wrong_shape_treated_as_missing_all():
    v = configchange_verdict(_event(), settings_json={"hooks": "not-a-dict"})
    assert v.evaluated is True
    assert set(v.missing_events) == {"PreToolUse", "PostToolUse", "Stop"}
    assert v.fires is True


# --- managed-flag entries count as wired, matching install.py / gate.self_wired semantics --------
def test_managed_flag_entries_count_as_wired():
    settings = {"hooks": {
        "PreToolUse": [{"_makoto_managed": True, "matcher": "*",
                         "hooks": [{"type": "command", "command": "/home/u/.claude/makoto_state/dispatch.sh"}]}],
        "PostToolUse": [{"_makoto_managed": True, "matcher": "*",
                          "hooks": [{"type": "command", "command": "/home/u/.claude/makoto_state/dispatch.sh"}]}],
        "Stop": [{"_makoto_managed": True, "matcher": "*",
                  "hooks": [{"type": "command", "command": "/home/u/.claude/makoto_state/dispatch.sh"}]}],
    }}
    v = configchange_verdict(_event(), settings_json=settings)
    assert v.fires is False


# --- caller-supplied settings_json wins over fs_read (documented precedence) ---------------------
def test_settings_json_takes_precedence_over_fs_read():
    def _boom(path):
        raise AssertionError("fs_read must not be called when settings_json is supplied")
    v = configchange_verdict(_event(), settings_json=_settings(), fs_read=_boom)
    assert v.evaluated is True
    assert v.fires is False


def test_fs_read_is_called_with_the_events_config_path():
    seen = {}

    def _reader(path):
        seen["path"] = path
        return json.dumps(_settings())

    v = configchange_verdict(_event(config_path=".claude/settings.local.json"), fs_read=_reader)
    assert seen["path"] == ".claude/settings.local.json"
    assert v.evaluated is True
    assert v.fires is False


# --- event shape flexibility: dict or attribute-bearing object -----------------------------------
def test_event_as_attribute_object_also_works():
    class Event:
        config_source = "project_settings"
        config_path = ".claude/settings.json"
    v = configchange_verdict(Event(), settings_json=_settings(pre=False))
    assert v.applicable is True
    assert v.missing_events == ("PreToolUse",)
    assert v.fires is True


# --- reason string is populated either way (audit/log friendliness) ------------------------------
def test_reason_present_on_every_verdict_shape():
    clean = configchange_verdict(_event(), settings_json=_settings())
    fired = configchange_verdict(_event(), settings_json=_settings(post=False))
    not_applicable = configchange_verdict(_event(config_source="skills"))
    not_evaluated = configchange_verdict(_event())
    for v in (clean, fired, not_applicable, not_evaluated):
        assert isinstance(v.reason, str) and v.reason
