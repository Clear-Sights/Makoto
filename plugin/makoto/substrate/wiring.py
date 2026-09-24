"""makoto.substrate.wiring -- hook-wiring introspection, the shared L0 home.

ONE domain: does a settings.json hook entry functionally reach makoto's dispatch? Consumed by
BOTH sides of the wiring contract -- install.py (the writer/status reporter) and
checks/otherPoint.py (the self-defense gate that detects partial stripping). The gate-side
layering firewall (tests/test_import_direction.py) forbids a gate importing install.py's
lifecycle machinery, but an L0 primitive module is precisely what the firewall allowlists.
Stdlib-only, no makoto-internal imports: safe for anything to depend on.
"""
from __future__ import annotations

import json
import os
import re

# The managed-entry marker `makoto install` writes into settings.json hook entries.
MAKOTO_CLAUDE_FLAG = "_makoto_managed"

# The plugin manifest's own path, relative to a resolved plugin root (matches hooks/hooks.json
# in this repo, the same file Claude Code reads to wire PreToolUse/PostToolUse/Stop/SubagentStop/
# SessionStart to ${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh for a plugin-packaged install).
PLUGIN_MANIFEST_RELPATH = os.path.join("hooks", "hooks.json")


# makoto's own hook-command invocation tokens -- anchored to the forms THIS TREE actually
# installs, and ONLY those: `~/.claude/makoto_state/dispatch.sh` (settings.json wiring;
# two-segment path so a bare `dispatch.sh` living anywhere else doesn't match),
# `${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh` (the plugin-manifest shim form, anchored the
# same way plus a trailing `\b` so a foreign or decoy filename never reads as makoto's), and the
# module forms `-m makoto.dispatch` / `-m makoto.configchange` (`\b` so `makoto.dispatcher_v2`
# never matches).
#
# An ownership predicate that recognizes a filename nothing installs is a standing licence to
# delete a file makoto did not write, so no unused form is kept "just in case".
#
# This ONE regex is the single source for "is this command makoto's" -- exported for
# `checks/selfMuteGuard` to import rather than maintain its own copy. A bare `makoto` substring
# test would (a) match ANY makoto subcommand, letting install/uninstall absorb and delete a
# user's own makoto-CLI hooks, and (b) let a decoy hook merely NAMING makoto satisfy
# `gate.self_wired`'s wired-check, suppressing the self-defense gate.
# `re.IGNORECASE`: Windows/case-insensitive filesystems can produce either casing for a path
# makoto itself wrote.
MAKOTO_INVOCATION_RX = re.compile(
    r"makoto_state[/\\]dispatch\.sh"
    r"|makoto[/\\]_dispatch_shim\.sh\b"
    r"|-m\s+makoto\.(?:dispatch|configchange)\b",
    re.IGNORECASE)


def entry_dispatches_to_makoto(entry) -> bool:
    """True iff ONE hook entry functionally reaches makoto's dispatch -- the managed-flag entry
    `makoto install` writes, or a flag-less hand-wired/shim entry whose command is one of
    makoto's own invocation forms (`MAKOTO_INVOCATION_RX`).

    This is the SAME predicate used to decide ownership for absorption and removal
    (`entry_owned_by_makoto` is an alias): a split predicate would let a decoy hook that merely
    NAMES makoto satisfy detection while a real makoto CLI invocation fails the narrower one.
    Keying on the flag alone lies on a shim-wired device (status reports unwired while it
    fires; install double-dispatches a duplicate entry)."""
    if not isinstance(entry, dict):
        return False
    if entry.get(MAKOTO_CLAUDE_FLAG):
        return True
    return _entry_command_invokes_makoto(entry)


def _entry_command_invokes_makoto(entry) -> bool:
    """True iff one of the entry's hook COMMANDS is a makoto invocation form
    (`MAKOTO_INVOCATION_RX`). The functional half of the wiring question: `event_wired` keys on
    this, so a `_makoto_managed` entry whose command was gutted to a no-op reads UNWIRED. A None
    "hooks" value is an unwired entry, never a raise: this input is reachable from
    attacker-controlled settings.json content."""
    if not isinstance(entry, dict):
        return False
    return any(isinstance(inner, dict)
               and MAKOTO_INVOCATION_RX.search(str(inner.get("command", "")))
               for inner in entry.get("hooks") or ())


# Removal and absorption need the SAME question detection answers -- see
# `entry_dispatches_to_makoto`.
entry_owned_by_makoto = entry_dispatches_to_makoto


def event_wired(hooks, event: str) -> bool:
    """True iff a hooks-shaped dict (either settings.json's own "hooks" key, or a plugin
    manifest's "hooks" key -- same shape, same semantics) wires `event` to makoto. This is not
    "does a file exist", it is "does a real entry for this exact event name makoto".

    Keys on `_entry_command_invokes_makoto`, NOT on `entry_dispatches_to_makoto`: the
    `_makoto_managed` flag alone must never read as wired, since anyone editing settings.json can
    strip the command while keeping the flag. Ownership (absorption/removal) and wiredness are
    answered separately."""
    if not isinstance(hooks, dict):
        return False
    return any(_entry_command_invokes_makoto(h) for h in hooks.get(event, []) or ())


def read_plugin_manifest_hooks(plugin_root, fs_read) -> dict:
    """Best-effort read of <plugin_root>/hooks/hooks.json's own "hooks" dict, or {} on ANY
    failure. Fails CLOSED toward "confirms nothing" -- {} never suppresses a gate.self_wired
    finding, only an actually-parsed, actually-declaring manifest can. `plugin_root` should be
    the live $CLAUDE_PLUGIN_ROOT, never a guessed/cached path, so an unresolvable root degrades
    to alarm rather than silent-wired."""
    if not plugin_root:
        return {}
    try:
        raw = fs_read(os.path.join(plugin_root, PLUGIN_MANIFEST_RELPATH))
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    hooks = data.get("hooks")
    return hooks if isinstance(hooks, dict) else {}
