"""Security fix (ported from the stale public-repo branch's 8fec86e): ONE exported, anchored,
case-insensitive invocation-token regex (`wiring.MAKOTO_INVOCATION_RX`) answers "is this command
makoto's" everywhere -- detection, absorption, removal, the self-mute guard, and the self-wired
gate -- instead of a bare `"makoto" in command` substring test plus selfMuteGuard's own drifted
hand-rolled copy.

What the one regex closes, each pinned below:
  (a) overbroad ownership: `-m makoto.status` / `-m makoto.reference_integrity` -- a user's OWN
      makoto-CLI hooks -- satisfied the substring test, so install absorbed (deleted) them and
      uninstall would remove them: "silently disarmed the user's own integrity hook".
  (b) decoy suppression: a hook merely NAMING makoto (`echo makoto`) satisfied
      `entry_dispatches_to_makoto`, so `gate.self_wired` read a stripped event as still wired --
      a false-negative in the self-defense gate.
  (c) selfMuteGuard's drifted copy (`makoto_state|dispatch\\.sh`, unanchored): false-BLOCKed an
      edit to a user's own unrelated `/usr/local/bin/dispatch.sh` hook, while MISSING the plugin
      manifest's `_dispatch_shim.sh` form entirely (gutting a plugin-packaged install was
      invisible to the guard).

Reproduction discipline: every test below marked RED-before was run against the unfixed tree and
failed, then passed with the fix applied.
"""
from __future__ import annotations

import json

from makoto.checks import selfMuteGuard
from makoto.substrate.wiring import (
    MAKOTO_INVOCATION_RX,
    entry_dispatches_to_makoto,
    entry_owned_by_makoto,
    event_wired,
)


def _entry(cmd: str) -> dict:
    return {"hooks": [{"type": "command", "command": cmd}]}


# ---- (a) the user's own makoto-CLI hooks are NOT makoto's dispatch ---------------------------
def test_a_users_own_makoto_cli_hook_is_not_owned():          # RED-before
    for cmd in ("python3 -m makoto.status",
                "python3 -m makoto.reference_integrity --strict",
                "makoto-lint --fix"):
        assert entry_dispatches_to_makoto(_entry(cmd)) is False, cmd
        assert entry_owned_by_makoto(_entry(cmd)) is False, cmd


def test_makotos_own_installed_forms_are_owned():
    for cmd in ("/home/u/.claude/makoto_state/dispatch.sh",
                "C:\\Users\\u\\.claude\\MAKOTO_STATE\\DISPATCH.SH",       # case/sep variant
                "${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh",
                "python3 -m makoto.dispatch",
                "PYTHON3 -M MAKOTO.DISPATCH"):
        assert entry_dispatches_to_makoto(_entry(cmd)) is True, cmd
    assert entry_dispatches_to_makoto({"_makoto_managed": True}) is True


def test_owned_and_dispatches_are_the_same_predicate():
    """Detection and removal must answer ONE question -- a split predicate is what let a decoy
    satisfy one side and a real invocation fail the other."""
    assert entry_owned_by_makoto is entry_dispatches_to_makoto


def test_module_form_does_not_swallow_other_makoto_submodules():
    assert MAKOTO_INVOCATION_RX.search("python3 -m makoto.dispatcher_v2") is None
    assert MAKOTO_INVOCATION_RX.search("python3 -m makoto.configchange") is not None


# ---- (b) a decoy hook merely naming makoto must not read as wired ----------------------------
def test_decoy_hook_naming_makoto_does_not_suppress_self_wired():   # RED-before
    decoy = {"PreToolUse": [_entry("echo makoto is watching")]}
    assert event_wired(decoy, "PreToolUse") is False
    real = {"PreToolUse": [_entry("${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh")]}
    assert event_wired(real, "PreToolUse") is True


# ---- (c) selfMuteGuard imports the ONE regex, not a drifted copy ------------------------------
def test_mute_guard_uses_the_shared_invocation_regex():
    assert selfMuteGuard._MAKOTO_CMD_RX is MAKOTO_INVOCATION_RX


def _mute_predicate(old: str, new: str):
    return selfMuteGuard.predicate(
        current_event={"hook_event_name": "PreToolUse",
                       "tool_input": {"file_path": "/home/u/.claude/settings.json",
                                      "old_string": old, "new_string": new}},
        history=[], pattern=selfMuteGuard.CHECK)


def test_mute_guard_does_not_false_block_a_users_own_dispatch_sh():   # RED-before
    old = json.dumps(_entry("/usr/local/bin/dispatch.sh"))
    assert _mute_predicate(old, "{}") is None


def test_mute_guard_catches_gutting_the_plugin_shim_form():           # RED-before
    old = json.dumps(_entry("${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh"))
    f = _mute_predicate(old, json.dumps(_entry("true")))
    assert f is not None and "guts makoto's hook command" in f.message


def test_mute_guard_still_catches_gutting_the_settings_form():
    old = json.dumps(_entry("/home/u/.claude/makoto_state/dispatch.sh"))
    f = _mute_predicate(old, json.dumps(_entry("true")))
    assert f is not None
