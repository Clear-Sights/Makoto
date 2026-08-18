"""The EVENT surface matrix — mirrors Detent's tests/test_events.py exactly in shape.

"Did you even look at all the hooks?" must be structurally impossible to ask twice: EVENTS
declares a disposition for EVERY hook event the harness documents — WIRED (a real handler
attached), HOLE (named, honestly unbuilt or built-but-unshipped), or OUT (declared out of scope,
with reason). Reconciled these ways: against the pinned full event list (the harness settings
schema's own enum, the SAME pin Detent uses — same harness, same events); against
hooks/hooks.json (every wired event is actually wired, to the real dispatcher, not just any
command; nothing wired is undeclared); and against the real source of any file a disposition
makes a code-existence claim about. Makoto has no MOVES lookup table the way Detent does (its
dispatch is a single orchestrator, not a table), so "does this named handler still exist" is
checked by real AST traversal of the claimed file, not substring search — a name surviving only
in a comment, a docstring, or dead code after the real reference is deleted must NOT pass.
"""
import ast
import json
from pathlib import Path

from makoto.events import EVENTS

REPO = Path(__file__).resolve().parent.parent

# The harness's own hook-event enum (settings schema + hooks reference, 2026-07-10) — the same
# pin Detent's tests/test_events.py uses, since both faculties sit on the same harness. This is a
# SHARED assumption, not two independent confirmations: if the harness ships event #31, both
# repos' pins go stale together and neither test catches it alone. A harness release adding an
# event makes this test STALE, not silently incomplete — update the pin here (and in Detent's
# copy) and give the new event a disposition.
DOCUMENTED_EVENTS = {
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "PostToolBatch", "Notification",
    "UserPromptSubmit", "UserPromptExpansion", "SessionStart", "SessionEnd", "Stop",
    "StopFailure", "SubagentStart", "SubagentStop", "PreCompact", "PostCompact",
    "PermissionRequest", "PermissionDenied", "Setup", "TeammateIdle", "TaskCreated",
    "TaskCompleted", "Elicitation", "ElicitationResult", "ConfigChange", "WorktreeCreate",
    "WorktreeRemove", "InstructionsLoaded", "CwdChanged", "FileChanged", "MessageDisplay",
}


def _referenced_names(source: str) -> set[str]:
    """Every dotted name genuinely used as CODE in `source` — a Name, an Attribute chain (both
    the full dotted chain and its final component), or a def/class target. Real AST traversal,
    not text search: a docstring or a comment is a Constant/not-parsed at all, never a Name or
    Attribute node, so a handler name can't survive here by sitting in prose after the real
    reference is deleted."""
    found: set[str] = set()

    def dotted(node: ast.Attribute) -> str | None:
        parts = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
            full = dotted(node)
            if full:
                found.add(full)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


def test_every_documented_event_has_a_disposition():
    assert set(EVENTS) == DOCUMENTED_EVENTS


def test_dispositions_are_legal_and_reasoned():
    for name, entry in EVENTS.items():
        assert entry["status"] in ("WIRED", "HOLE", "OUT"), name
        if entry["status"] == "WIRED":
            assert entry.get("moves"), f"{name}: WIRED without moves"
        else:
            assert entry.get("reason"), f"{name}: {entry['status']} without a reason"


def test_hooks_json_wires_exactly_the_wired_events():
    wired = {name for name, e in EVENTS.items() if e["status"] == "WIRED"}
    hooks = json.loads((REPO / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == wired


def test_hooks_json_wired_events_point_at_the_real_dispatcher():
    """Key presence alone doesn't prove wiring — a stray matcher pointing at some other command
    would pass a set-equality check. Every WIRED event's command must actually route to Makoto's
    own dispatcher, not merely exist under the right key."""
    hooks = json.loads((REPO / "hooks" / "hooks.json").read_text())["hooks"]
    wired = {name for name, e in EVENTS.items() if e["status"] == "WIRED"}
    for name in wired:
        commands = [h["command"] for matcher in hooks[name] for h in matcher["hooks"]]
        assert any("_dispatch_shim.sh" in c or "makoto.dispatch" in c for c in commands), \
            f"{name}: no command routes to makoto's dispatcher: {commands}"


def test_posttoolusefailure_uses_the_post_accumulation_route():
    from makoto.dispatch import HANDLERS, _EVENT_MAP, _HOOK_TO_EDGE, _accumulate

    assert HANDLERS["PostToolUseFailure"] is _accumulate
    assert _HOOK_TO_EDGE["PostToolUseFailure"] == "Post"
    assert _EVENT_MAP["PostToolUseFailure"] == "live.post_tool_use_failure"


def test_wired_moves_appear_in_dispatch_source():
    names = _referenced_names((REPO / "makoto" / "dispatch.py").read_text())
    for name, entry in EVENTS.items():
        if entry["status"] != "WIRED":
            continue
        for move_name in entry["moves"]:
            assert move_name in names, f"{name}: {move_name!r} not referenced in dispatch.py"


# HOLE entries that assert specific code still exists — each maps to (file, anchor names) so a
# deleted branch turns this matrix into a silent lie without this check. Only entries making a
# checkable code claim are listed. (SessionStart/SubagentStop graduated HOLE→WIRED 2026-07-12,
# and PostToolUseFailure graduated HOLE→WIRED 2026-08-18 — their anchors now live in the WIRED
# moves check above.)
_HOLE_CODE_ANCHORS = {
    "ConfigChange": ("makoto/configchange.py", ("configchange_verdict",)),
}


def test_hole_code_claims_still_exist():
    for name, (rel_path, anchors) in _HOLE_CODE_ANCHORS.items():
        assert EVENTS[name]["status"] == "HOLE", name
        names = _referenced_names((REPO / rel_path).read_text())
        for anchor in anchors:
            assert anchor in names, f"{name}: {anchor!r} not referenced in {rel_path}"
