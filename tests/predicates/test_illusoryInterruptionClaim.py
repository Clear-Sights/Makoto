"""Unit tests for content.illusory_interruption_claim — a fabricated "interrupted by user"
excuse with no genuine harness-set interruption anywhere in the session's own history.

Covers both creation points (Bash commit command + Write/Edit introduced content), the
history-grounding short-circuit (a REAL interrupted:true row makes the claim true, not
illusory), the makoto-allow exemption, case-insensitivity, and the PreToolUse-only / empty-
text guards.
"""
from __future__ import annotations
import importlib
from makoto.core.schema import PreCheck

MOD = importlib.import_module("makoto.checks.illusoryInterruptionClaim")
PAT = PreCheck(id="content.illusory_interruption_claim", fire_level="error",
              description="illusory interruption claim", retry_hint="remove it")

# makoto-allow: test fixtures must carry the literal claim to exercise the detector
_CLAIM = "[Request interrupted by user]"


def _bash(command: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}}


def _write(content: str, file_path: str = "notes.md") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content}}


def _fire(evt: dict, history: list | None = None):
    return MOD.predicate(current_event=evt, history=history or [], pattern=PAT)


def _real_interruption_row():
    import json
    payload = {"tool_name": "Bash", "tool_input": {"command": "long_running_cmd"},
               "tool_response": {"stdout": "", "stderr": "", "interrupted": True}}
    return {"payload": json.dumps(payload)}


# --- TP: fires with no genuine interruption on record -----------------------
def test_fires_on_bracketed_harness_marker_in_written_content():
    f = _fire(_write(f"Stopped here: {_CLAIM}\n"))
    assert f is not None and f.pattern_id == "content.illusory_interruption_claim"


def test_fires_on_commit_message_claim():
    cmd = f'git commit -m "wip: {_CLAIM}"'
    assert _fire(_bash(cmd)) is not None


def test_fires_on_prose_paraphrase():
    assert _fire(_write("I stopped because I was interrupted by the user.\n")) is not None
    assert _fire(_write("Note: user interrupted mid-task.\n")) is not None


def test_fires_case_insensitive():
    assert _fire(_write("[request interrupted by user]\n")) is not None


def test_fires_on_edit_new_string():
    evt = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
           "tool_input": {"file_path": "x.md", "new_string": _CLAIM}}
    assert _fire(evt) is not None


# --- TN: a REAL interruption on record grounds the claim ---------------------
def test_silent_when_a_genuine_interruption_is_in_history():
    f = _fire(_write(f"Stopped here: {_CLAIM}\n"), history=[_real_interruption_row()])
    assert f is None


# --- TN: everything else stays silent -----------------------------------------
def test_makoto_allow_exempts():
    content = f"{_CLAIM}\n# makoto-allow: documenting the marker verbatim"
    assert _fire(_write(content)) is None


def test_unrelated_content_silent():
    assert _fire(_bash('git commit -m "fix: unrelated, no claim"')) is None
    assert _fire(_write("def f():\n    return 1\n")) is None


def test_non_pretooluse_silent():
    evt = {"hook_event_name": "Stop", "tool_name": "Bash", "tool_input": {"command": _CLAIM}}
    assert _fire(evt) is None


def test_empty_input_silent():
    assert _fire({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                  "tool_input": {}}) is None


def test_malformed_history_row_skipped_not_grounding():
    """A garbage history row must be skipped (fail-open), never mistaken for grounding."""
    f = _fire(_write(f"Stopped here: {_CLAIM}\n"), history=[{"payload": "not json"}, None, 42])
    assert f is not None
