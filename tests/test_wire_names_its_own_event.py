"""A rendered decision must not name an event other than the one it answers.

`_emit_decision` chose its wire with `_HOOK_TO_EDGE.get(hook_event, "Pre")`. Five of the six
hooks Makoto registers are mapped; `SessionStart` is not, and the host does send it. So a
finding on a SessionStart event rendered

    {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": ...}}

which tells the host the event was a tool pre-flight when it was a session start, and applies
a tool-permission decision to an event containing no tool. That is worse than not firing: not
firing is silence, this is a confident answer to a question nobody asked.

`verdict.dispatch_posture` already returns {} for an edge its table does not carry -- no wire,
no decision -- so the fix was to stop aliasing and pass the hook through as its own edge. The
finding is still written by `_record_audit` either way, so nothing drops the record of a fire;
only the mislabelled body goes.

These laws hold the property rather than the fix: any future hook added to hooks.json without
a wire renders nothing, and no hook ever renders under another hook's name.
"""
from __future__ import annotations

import inspect
import io
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugin"))

import makoto.dispatch as dispatch                      # noqa: E402
from makoto.dispatch import Finding, _HOOK_TO_EDGE      # noqa: E402
from makoto.registry import ALLOWED_EDGES, load_checks  # noqa: E402


def _probe() -> Finding:
    required = {name: "" for name, p in inspect.signature(Finding).parameters.items()
                if p.default is inspect.Parameter.empty}
    named = {k: v for k, v in (("pattern_id", "probe"), ("message", "m"), ("level", "error"))
             if k in inspect.signature(Finding).parameters}
    return Finding(**{**required, **named})


def _render(hook_event: str) -> str:
    out = io.StringIO()
    dispatch._emit_decision([_probe()], hook_event, stream=out)
    return out.getvalue().strip()


def _registered() -> set[str]:
    return set(json.loads((REPO / "plugin/hooks/hooks.json").read_text())["hooks"])


class WireNamesItsOwnEvent(unittest.TestCase):
    def test_no_hook_renders_under_another_hooks_name(self):
        """The defect itself, as a law over every registered hook."""
        for hook in sorted(_registered() | {"Notification"}):
            with self.subTest(hook=hook):
                body = _render(hook)
                if not body:
                    continue
                named = json.loads(body)
                claimed = (named.get("hookSpecificOutput", {}).get("hookEventName")
                           or named.get("hookEventName"))
                if claimed is None:
                    continue
                self.assertEqual(
                    claimed, hook,
                    f"a finding on {hook} rendered a body claiming to be {claimed}. A host "
                    f"reading that applies {claimed}'s semantics to a {hook} event.")

    def test_an_unmapped_hook_renders_no_decision(self):
        """No wire, no decision -- not a decision on somebody else's wire."""
        for hook in sorted(_registered() - set(_HOOK_TO_EDGE)):
            with self.subTest(hook=hook):
                self.assertEqual(
                    _render(hook), "",
                    f"{hook} has no entry in _HOOK_TO_EDGE, so it has no wire of its own; it "
                    f"must render nothing rather than borrow one")

    def test_mapped_hooks_still_render(self):
        """Non-vacuity. Without this the laws above pass by nothing ever rendering."""
        rendered = [hook for hook in sorted(set(_HOOK_TO_EDGE) & _registered()) if _render(hook)]
        self.assertGreaterEqual(
            len(rendered), 3,
            "the mapped hooks must still emit their bodies; if they stopped, the two laws "
            "above would pass vacuously")

    def test_every_allowed_edge_is_reachable_or_unused_on_purpose(self):
        """An edge a check may declare but the dispatcher can never deliver is a check that
        loads clean and never fires. Recorded with its denominator rather than asserted away:
        prechecks are selected by keyword, not edge, and the only edge-conditional invocation
        is the Stop/SubagentStop branch, so `applies_at` gates the Stop gates alone."""
        declared = {getattr(c, "applies_at", None) for c in load_checks()}
        unused = sorted(ALLOWED_EDGES - declared)
        self.assertEqual(
            unused, ["Post", "SessionStart", "SubagentStop"],
            "the set of allowed-but-unused edges changed. That is not automatically wrong, "
            "but it is a decision: a new edge with no check is headroom, and a check on an "
            "edge the dispatcher cannot deliver never fires. Update this list deliberately.")


if __name__ == "__main__":
    unittest.main()
