"""The model-judged rows: register entries whose witness is a judgement no record read makes
(B7 B10 B21 B34) are `type: "prompt"` PreToolUse hooks in the plugin's own hooks.json, each scoped
by `if` to the files the rule can apply to. The judgement itself cannot run offline, so these pin
the entry: present, scoped, blocking on `ok: false`, and its prompt carries the register's own fix
line. Removing an entry turns its case red. Live-probed 2026-09-25 (B7): a Write of CLAUDE.md adding
"Always run the linter before committing" was denied with the B7 reason."""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOKS = json.loads((ROOT / "plugin" / "hooks" / "hooks.json").read_text())
REGISTER = (ROOT / "docs" / "REGISTER.md").read_text()

_SCOPE = {"B7": ("CLAUDE.md", "AGENTS.md"), "B10": ("check",), "B21": ("test_",), "B34": ("check",)}


def _fix_line(entry: str) -> str:
    m = re.search(rf"^{entry}\s+[A-Z].*\n.*\n\s+> (.+)$", REGISTER, re.M)
    assert m, entry
    return m.group(1).rstrip(";").strip()


def _entries(entry: str) -> list:
    return [h for m in HOOKS["hooks"]["PreToolUse"] for h in m["hooks"]
            if h.get("type") == "prompt" and h.get("statusMessage") == f"makoto {entry}"]


@pytest.mark.parametrize("entry", sorted(_SCOPE))
def test_judged_entry_is_a_scoped_prompt_hook_naming_its_fix_line(entry):
    hooks = _entries(entry)
    assert hooks, f"{entry}: no prompt hook"
    fix = _fix_line(entry)
    for h in hooks:
        assert re.fullmatch(r"(Write|Edit)\(\*\*/[^)]+\)", h.get("if", "")), f"{entry}: unscoped {h.get('if')}"
        assert any(s in h["if"] for s in _SCOPE[entry])
        assert fix in h["prompt"], f"{entry}: prompt lacks the fix line {fix!r}"
        assert '"ok": false' in h["prompt"] and "$ARGUMENTS" in h["prompt"]
        assert h.get("continueOnBlock") is True, "the reason must reach the agent so it can discharge in-turn"
    assert {h["if"].split("(")[0] for h in hooks} == {"Write", "Edit"}
