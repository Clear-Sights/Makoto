"""makoto.substrate.wiring -- hook-wiring introspection, the shared L0 home.

ONE domain: does a settings.json hook entry functionally reach makoto's dispatch? Consumed by
BOTH sides of the wiring contract -- install.py (the writer/status reporter) and
checks/selfWiredCheck.py (the self-defense gate that detects partial stripping). Hoisted here
2026-07-09 from the byte-for-byte duplicate both files carried: selfWiredCheck's own module
note asked for exactly this ("a future refactor that hoists both to a shared L0 module would
let this duplication go away") -- the gate-side layering firewall
(tests/test_gate_shape.py, ALLOWED_IMPORT_ROOTS) forbids a gate importing install.py's
lifecycle machinery, but an L0 primitive module is precisely what the firewall allowlists.
Stdlib-only, no makoto-internal imports: safe for anything to depend on.
"""
from __future__ import annotations

import json
import os

# The managed-entry marker `makoto install` writes into settings.json hook entries.
MAKOTO_CLAUDE_FLAG = "_makoto_managed"

# The plugin manifest's own path, relative to a resolved plugin root (matches hooks/hooks.json
# in this repo, the same file Claude Code reads to wire PreToolUse/PostToolUse/Stop/SubagentStop/
# SessionStart to ${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh for a plugin-packaged install).
PLUGIN_MANIFEST_RELPATH = os.path.join("hooks", "hooks.json")


def entry_dispatches_to_makoto(entry) -> bool:
    """True iff ONE hook entry functionally reaches makoto's dispatch -- the managed-flag entry
    `makoto install` writes, OR a flag-less hand-wired/shim entry whose command names makoto
    (`.../makoto_state/dispatch.sh`, `python -m makoto._dispatch`). Keying on the flag alone
    lies on a shim-wired device (status: hooks_wired=false while firing, fixed v1.2.1;
    install: a duplicate entry double-dispatching every event, the same bug on the write side)."""
    if not isinstance(entry, dict):
        return False
    if entry.get(MAKOTO_CLAUDE_FLAG):
        return True
    return any(isinstance(inner, dict) and "makoto" in str(inner.get("command", "")).lower()
               for inner in entry.get("hooks", []))


def event_wired(hooks, event: str) -> bool:
    """True iff a hooks-shaped dict (either settings.json's own "hooks" key, or a plugin
    manifest's "hooks" key -- same shape, same semantics) wires `event` to makoto. Shared by both
    wiring sources so selfWiredCheck's two-source check applies IDENTICAL rigor to each -- this is
    not "does a file exist", it is "does a real entry for this exact event name makoto"."""
    if not isinstance(hooks, dict):
        return False
    return any(entry_dispatches_to_makoto(h) for h in hooks.get(event, []) or ())


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
