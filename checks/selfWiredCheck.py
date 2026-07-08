from __future__ import annotations
import json
from typing import Optional
from makoto.schema import Finding
from makoto.checks._shared import StopCheck


# Mirrors makoto.install._MAKOTO_CLAUDE_FLAG / ._entry_dispatches_to_makoto, duplicated here
# rather than imported: this package's layering firewall (tests/test_gate_shape.py,
# ALLOWED_IMPORT_ROOTS) restricts a gate module to L0/L1 primitives + the intra-package
# _shared helper — install.py is lifecycle/CLI machinery, not a primitive, and importing it
# would be a clean-cycle-wise but layering-wise import a gate module should not make. Keep this
# predicate's logic byte-for-byte in step with install.py's by hand; a future refactor that
# hoists both to a shared L0 module would let this duplication go away.
_MAKOTO_CLAUDE_FLAG = "_makoto_managed"
_MAKOTO_EVENTS = ("PreToolUse", "PostToolUse", "Stop")


def _entry_dispatches_to_makoto(entry) -> bool:
    """True iff ONE hook entry functionally reaches makoto's dispatch — the managed-flag entry
    `makoto install` writes, OR a flag-less hand-wired/shim entry whose command names makoto.
    Verbatim mirror of makoto.install._entry_dispatches_to_makoto (see module note above)."""
    if not isinstance(entry, dict):
        return False
    if entry.get(_MAKOTO_CLAUDE_FLAG):
        return True
    return any(isinstance(inner, dict) and "makoto" in str(inner.get("command", "")).lower()
               for inner in entry.get("hooks", []))


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


GATE = StopCheck(
    id="gate.self_wired",
    fn=self_wired_gate,
    run=lambda c: self_wired_gate(c.fs_read),
)


# NOTE (owner-revised deviation, logged): this CHECK's posture is "ADVISE", not "BLOCK" like every
# sibling Stop gate migrated in this same ticket. gate.self_wired's own Finding.level is documented
# and behaviorally pinned (tests/test_stop_gate_level_invariant.py) as ALWAYS "advisory", never
# "error" (the one FABLE-DECISION-cited advisory exception among the Stop gates, FD6 2026-07-05) —
# declaring it CHECK.posture="BLOCK" here would misrepresent that in the flat checks/ catalog's own
# metadata. This CHECK object is purely additive discovery metadata (Task 9's load_checks(edge=
# "Stop") seam) and does not change self_wired_gate's actual runtime behavior or its GATE/
# load_stopchecks() wiring, which are byte-for-byte unchanged from before this migration.
from makoto.checks._loader import Check as _Check
CHECK = _Check(id="gate.self_wired", applies_at="Stop", posture="ADVISE", run=GATE.run)
