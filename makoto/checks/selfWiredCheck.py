from __future__ import annotations
import json
from typing import Optional
from makoto.core.schema import Finding
# The 2026-07-09 dedup pass performed exactly the hoist this module's old note asked for: the
# wiring predicate now lives in makoto.substrate.wiring (an L0 primitive module, firewall-
# allowlisted in tests/test_gate_shape.py's ALLOWED_IMPORT_ROOTS), shared with install.py
# instead of mirrored by hand.
from makoto.substrate.wiring import entry_dispatches_to_makoto as _entry_dispatches_to_makoto

_MAKOTO_EVENTS = ("PreToolUse", "PostToolUse", "Stop")


def _missing_makoto_events(hooks) -> list:
    """[event, ...] for each of PreToolUse/PostToolUse/Stop that carries NO entry dispatching to
    makoto. Empty list means fully wired. Pure and side-effect-free so it can be exercised
    directly (predicate-only, no live settings.json needed) — see tests/test_stopcheck_self_wired.py."""
    if not isinstance(hooks, dict):
        return list(_MAKOTO_EVENTS)
    return [event for event in _MAKOTO_EVENTS
            if not any(_entry_dispatches_to_makoto(h) for h in hooks.get(event, []) or ())]


def self_wired_gate(fs_read) -> Optional[Finding]:
    """Partial-strip detection only: catches a settings.json edit that leaves at least one Makoto
    hook entry intact while removing another; a single edit that removes ALL of Makoto's
    PreToolUse/PostToolUse/Stop entries simultaneously disables this check itself in the same
    instant (Claude Code reloads hooks.json live, not cached once at session start — verified
    against code.claude.com/docs/en/settings.md, "When edits take effect"), so it provides ZERO
    coverage against that canonical full-strip attack. See docs/self-defense-asymmetry-followup.md
    for the fuller writeup; this check is recorded there as mitigation, not closure.

    Fires iff `.claude/settings.json` (repo-root-relative, read via `fs_read` — the same
    cwd-relative convention gate.dropped uses for its own fs_read calls) parses as a JSON object
    and at least one of PreToolUse/PostToolUse/Stop has no entry dispatching to makoto (managed-
    flag or hand-wired/shim; see `_entry_dispatches_to_makoto`). The message names exactly which
    event(s) lost their entry.

    ADVISORY tier only (`level="advisory"`, never `"error"`): per this repo's "advisory over
    blocking" standing policy and the explicit condition this check shipped under, it must never
    block a turn — `_emit_decision` in _dispatch.py maps level=="advisory" to posture.ADVISE, and
    wire.py's Stop/SubagentStop table has no ADVISE entry (only BLOCK renders there), so an
    advisory finding is recorded to the audit log (a forensic trail) and never surfaces as a
    block. Fail-open on anything short of a parseable JSON object at that path —
    missing file, unreadable, malformed JSON, or a non-dict payload all return None silently,
    matching every other gate's fail-open philosophy. (A settings.json that exists but was never
    wired to makoto at all — e.g. a fresh, un-configured file — produces the same "all three
    missing" signal as a full strip would; this check cannot and does not try to distinguish
    "never wired" from "just stripped".)"""
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
    missing = _missing_makoto_events(hooks if isinstance(hooks, dict) else {})
    if not missing:
        return None
    named = ", ".join(missing)
    return Finding(
        pattern_id="gate.self_wired",
        file=".claude/settings.json",
        line=0,
        level="advisory",
        message=(f"makoto's hook wiring in .claude/settings.json is missing an entry for: {named}. "
                 f"This is a PARTIAL-STRIP signal only — it cannot see a simultaneous strip of all "
                 f"three events (see this check's own docstring / "
                 f"docs/self-defense-asymmetry-followup.md)."),
        retry_hint=("Advisory only, never blocking: confirm this was an intentional change to "
                     "settings.json, or restore the missing hook entry via `makoto install`."),
    )


# NOTE (owner-revised deviation, logged): this CHECK's posture is "ADVISE", not "BLOCK" like every
# sibling Stop gate. gate.self_wired's own Finding.level is documented and behaviorally pinned
# (tests/test_stop_gate_level_invariant.py) as ALWAYS "advisory", never "error" (the one
# FABLE-DECISION-cited advisory exception among the Stop gates, FD6 2026-07-05) -- declaring it
# CHECK.posture="BLOCK" here would misrepresent that in the flat checks/ catalog's own metadata.
# `may_block=True` here is NOT a contradiction: it only says "structurally eligible IF posture
# were ever BLOCK" (it isn't, and is pinned as such by the test above) -- the actual never-blocks
# guarantee still rests on posture=="ADVISE", same as always.
from makoto.substrate._loader import Check as _Check
CHECK = _Check(id="gate.self_wired", applies_at="Stop", posture="ADVISE", may_block=True,
               run=lambda c: self_wired_gate(c.fs_read))
