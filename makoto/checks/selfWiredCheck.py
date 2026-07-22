from __future__ import annotations
import json
import os
from typing import Optional
from makoto.core.schema import Finding
# The 2026-07-09 dedup pass performed exactly the hoist this module's old note asked for: the
# wiring predicate now lives in makoto.substrate.wiring (an L0 primitive module, firewall-
# allowlisted in tests/test_gate_shape.py's ALLOWED_IMPORT_ROOTS), shared with install.py
# instead of mirrored by hand.
from makoto.substrate.wiring import (
    entry_dispatches_to_makoto as _entry_dispatches_to_makoto,
    event_wired as _event_wired,
    read_plugin_manifest_hooks as _read_plugin_manifest_hooks,
)

_MAKOTO_EVENTS = ("PreToolUse", "PostToolUse", "Stop")


def _default_plugin_fs_read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _missing_makoto_events(hooks, *, plugin_root=None, plugin_fs_read=None) -> list:
    """[event, ...] for each of PreToolUse/PostToolUse/Stop confirmed by NEITHER settings.json's
    own "hooks" key NOR the plugin manifest (2026-07-22 two-source fix: a plugin-packaged install
    legitimately wires makoto via hooks/hooks.json alone, and settings.json is never expected to
    duplicate it — this predicate now checks both before calling an event missing). Empty list
    means fully wired. `plugin_root` defaults to the live $CLAUDE_PLUGIN_ROOT and `plugin_fs_read`
    to a real file read when not supplied, so this stays pure/injectable for tests exactly like
    the settings.json side already is — see tests/test_self_wired_check.py."""
    settings_hooks = hooks if isinstance(hooks, dict) else {}
    still_missing = [event for event in _MAKOTO_EVENTS if not _event_wired(settings_hooks, event)]
    if not still_missing:
        return []
    root = plugin_root if plugin_root is not None else os.environ.get("CLAUDE_PLUGIN_ROOT")
    reader = plugin_fs_read if plugin_fs_read is not None else _default_plugin_fs_read
    plugin_hooks = _read_plugin_manifest_hooks(root, reader)
    return [event for event in still_missing if not _event_wired(plugin_hooks, event)]


def self_wired_gate(fs_read, *, plugin_root=None, plugin_fs_read=None) -> Optional[Finding]:
    """Partial-strip detection only: catches an edit that leaves at least one of makoto's
    PreToolUse/PostToolUse/Stop entries wired (in EITHER settings.json or the plugin manifest)
    while removing another; an edit that strips wiring from BOTH sources for ALL THREE events
    simultaneously disables this check itself in the same instant for the settings.json-only
    case (Claude Code reloads hooks.json live, not cached once at session start — verified
    against code.claude.com/docs/en/settings.md, "When edits take effect"), so it still provides
    ZERO coverage against that canonical full-strip attack. See docs/self-defense-asymmetry-followup.md
    for the fuller writeup; this check is recorded there as mitigation, not closure.

    TWO wiring sources, checked with IDENTICAL rigor (2026-07-22): `.claude/settings.json`'s own
    "hooks" key (repo-root-relative, read via `fs_read`), and — only for an event still missing
    there — the makoto plugin's own hooks/hooks.json manifest, resolved via `plugin_root`
    (defaults to the live $CLAUDE_PLUGIN_ROOT — the same pointer Claude Code substitutes into
    `${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh` itself, never a guessed/cached path) and read
    via `plugin_fs_read` (defaults to a real file read). Fires iff an event is confirmed by
    NEITHER source. The message names exactly which event(s) lost their entry.

    ADVISORY tier only (`level="advisory"`, never `"error"`): per this repo's "advisory over
    blocking" standing policy and the explicit condition this check shipped under, it must never
    block a turn — `_emit_decision` in _dispatch.py maps level=="advisory" to posture.ADVISE, and
    wire.py's Stop/SubagentStop table has no ADVISE entry (only BLOCK renders there), so an
    advisory finding is recorded to the audit log (a forensic trail) and never surfaces as a
    block. Fail-open on anything short of a parseable settings.json JSON object — missing file,
    unreadable, malformed JSON, or a non-dict payload all return None silently, matching every
    other gate's fail-open philosophy; the plugin-manifest side fails CLOSED instead (any read/
    resolution failure there degrades to "confirms nothing", never to silent-wired — an
    unresolvable/forged plugin_root must never suppress a real finding). This still cannot
    distinguish "never wired via settings.json, wired via the plugin instead" (now correctly
    silent) from "was stripped from settings.json AND the plugin manifest is also unreadable/
    unresolvable right now" (still fires) from a genuine simultaneous full strip of both sources
    (the documented blind spot above) — it reads disk state at check time, not the harness's own
    live-loaded hook table."""
    if fs_read is None:
        return None
    try:
        raw = fs_read(".claude/settings.json")
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    hooks = data.get("hooks")
    missing = _missing_makoto_events(hooks if isinstance(hooks, dict) else {},
                                      plugin_root=plugin_root, plugin_fs_read=plugin_fs_read)
    if not missing:
        return None
    named = ", ".join(missing)
    return Finding(
        pattern_id="gate.self_wired",
        file=".claude/settings.json",
        line=0,
        level="advisory",
        message=(f"makoto's hook wiring is missing an entry for: {named} in BOTH "
                 f".claude/settings.json and the plugin manifest (if resolvable). "
                 f"This is a PARTIAL-STRIP signal only — it cannot see a simultaneous strip of "
                 f"all three events from both sources at once (see this check's own docstring / "
                 f"docs/self-defense-asymmetry-followup.md)."),
        retry_hint=("Advisory only, never blocking: confirm this was an intentional change, or "
                     "restore the missing hook entry via `makoto install`."),
    )


# NOTE (owner-revised deviation, logged): this CHECK's posture is "ADVISE", not "BLOCK" like every
# sibling Stop gate. gate.self_wired's own Finding.level is documented and behaviorally pinned
# (tests/test_stop_gate_level_invariant.py) as ALWAYS "advisory", never "error" (the one
# DESIGN-DECISION-cited advisory exception among the Stop gates, FD6 2026-07-05) -- declaring it
# CHECK.posture="BLOCK" here would misrepresent that in the flat checks/ catalog's own metadata.
# `may_block=True` here is NOT a contradiction: it only says "structurally eligible IF posture
# were ever BLOCK" (it isn't, and is pinned as such by the test above) -- the actual never-blocks
# guarantee still rests on posture=="ADVISE", same as always.
from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.self_wired", applies_at="Stop", posture="ADVISE", may_block=True,
               run=lambda c: self_wired_gate(c.fs_read), layer="meta")
