"""makoto.substrate.wiring -- hook-wiring introspection, the shared L0 home.

ONE domain: does a settings.json hook entry functionally reach makoto's dispatch? Consumed by
BOTH sides of the wiring contract -- install.py (the writer/status reporter) and
checks/selfWiredCheck.py (the self-defense gate that detects partial stripping). Hoisted here
2026-07-09 from the byte-for-byte duplicate both files carried: selfWiredCheck's own module
note asked for exactly this ("a future refactor that hoists both to a shared L0 module would
let this duplication go away") -- the gate-side layering firewall
(tests/test_import_direction.py, the pipeline-order firewall) forbids a gate importing install.py's
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
# installs, and ONLY those: `~/.claude/makoto_state/dispatch.sh` (settings.json wiring, written
# by install.py's `_install_bash_scripts`/`_wire_claude_hooks`; two-segment path so a bare
# `dispatch.sh` living anywhere else does not match), `${CLAUDE_PLUGIN_ROOT}/makoto/
# _dispatch_shim.sh` (the ONE plugin-manifest shim form -- see hooks/hooks.json, which wires
# every declared event to that single script; matched below with the SAME two-segment
# `makoto[/\\]` directory anchor its dispatch.sh sibling carries, plus a trailing `\b`, so a
# foreign `/opt/other/_dispatch_shim.sh`, an `x_dispatch_shim.sh`, or a `_dispatch_shim.shhh`
# never reads as makoto's -- an unanchored basename made a third-party hook absorbable/deletable
# and let a decoy substring read as wired), and the module forms `-m makoto.dispatch` /
# `-m makoto.configchange` (the two hook entrypoints, both of which have a live `__main__`;
# `\b` so `makoto.dispatcher_v2` never matches).
#
# Deliberately NOT a verbatim copy of the pattern this fix carried on the branch it came from:
# that one also admitted `_dispatch_configchange_shim.sh`, a script this layout does not have
# (configchange is reached as `-m makoto.configchange`, its adapter having been merged into
# makoto/configchange.py). An ownership predicate that recognizes a filename nothing installs is
# a standing licence to delete a file makoto did not write -- the exact over-match this regex
# exists to close, so the alternative is dropped rather than kept "just in case". If a
# configchange shim is ever installed, this regex is the one place that has to learn about it.
#
# This ONE regex is the single source for "is this command makoto's" -- exported for
# `checks/selfMuteGuard` to import rather than maintain its own copy. Two regexes answering one
# question is exactly the class of bug this module exists to prevent (see the module docstring):
# a bare `makoto` substring test invented a looser answer that (a) via matching ANY makoto
# subcommand -- `-m makoto.reference_integrity`, `-m makoto.status` -- let install/uninstall
# absorb and delete a user's OWN makoto-CLI hooks, the exact "silently disarmed the user's own
# integrity hook" failure this predicate exists to prevent, and (b) let a decoy hook merely
# NAMING makoto satisfy `gate.self_wired`'s wired-check, suppressing the self-defense gate.
# `re.IGNORECASE`: Windows/case-insensitive filesystems can produce either casing for a path
# makoto itself wrote, and the substring test this replaces was case-insensitive too -- a
# case-sensitive replacement would silently un-recognize a form makoto had already installed.
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
    (`entry_owned_by_makoto` is an alias of this function) -- detecting a wiring and being
    entitled to delete it are the same question once the invocation check is precise, and a
    split predicate is exactly what would let the two drift (a decoy hook that merely NAMES
    makoto satisfying detection while a real makoto CLI invocation fails the narrower one).
    Keying on the flag alone lies on a shim-wired device (status: hooks_wired=false while
    firing, fixed v1.2.1; install: a duplicate entry double-dispatching every event, the same
    bug on the write side)."""
    if not isinstance(entry, dict):
        return False
    if entry.get(MAKOTO_CLAUDE_FLAG):
        return True
    return _entry_command_invokes_makoto(entry)


def _entry_command_invokes_makoto(entry) -> bool:
    """True iff one of the entry's hook COMMANDS is a makoto invocation form
    (`MAKOTO_INVOCATION_RX`). The functional half of the wiring question: this is what
    `event_wired` keys on, so a `_makoto_managed` entry whose command was gutted to a no-op
    reads UNWIRED -- the flag is ownership metadata anyone editing settings.json can keep
    while stripping the command, so it is over-sufficient as a wiredness signal even though
    it stays sufficient for ownership (absorption/removal). A None "hooks" value is an
    unwired entry, never a raise: this input is reachable from attacker-controlled
    settings.json content, and a raise here would be swallowed per-predicate at the gate
    (dispatch's per-predicate guard) into a silent fail-open."""
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
    manifest's "hooks" key -- same shape, same semantics) wires `event` to makoto. Shared by both
    wiring sources so selfWiredCheck's two-source check applies IDENTICAL rigor to each -- this is
    not "does a file exist", it is "does a real entry for this exact event name makoto".

    Keys on `_entry_command_invokes_makoto`, NOT on `entry_dispatches_to_makoto`: the
    `_makoto_managed` flag alone must never read as wired. The flag is ownership metadata --
    anyone who can edit settings.json can strip the command while keeping the flag, and
    `entry_dispatches_to_makoto`'s docstring reasons only about the flag being INsufficient,
    never about it being OVER-sufficient. A gutted managed entry (`{"_makoto_managed": true,
    "hooks": [{"command": "true"}]}`, or no "hooks" key at all) reaches nothing, so it is
    unwired -- ownership (absorption/removal) and wiredness are answered separately."""
    if not isinstance(hooks, dict):
        return False
    return any(_entry_command_invokes_makoto(h) for h in hooks.get(event, []) or ())


def read_plugin_manifest_hooks(plugin_root, fs_read) -> dict:
    """Best-effort read of <plugin_root>/hooks/hooks.json's own "hooks" dict, or {} on ANY
    failure (no plugin_root, unreadable, malformed JSON, non-dict payload, non-dict "hooks").
    Fails CLOSED toward "confirms nothing" -- {} never suppresses a gate.self_wired finding,
    only an actually-parsed, actually-declaring manifest can. `plugin_root` should be the live
    $CLAUDE_PLUGIN_ROOT (the same pointer Claude Code substitutes into the hook command itself),
    never a guessed/cached path -- a forged or stale root would make this a decoy an attacker
    could plant, not a live wiring signal; a genuinely unresolvable root must degrade to alarm
    (report missing), never to silent-wired."""
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
