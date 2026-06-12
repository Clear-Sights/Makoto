"""Unit tests for pattern 1.34 — illusory Claude-authorship trailer.

Covers both creation points (Bash commit command + Write/Edit introduced content),
the Claude-gating that lets a genuine human co-author pass, the makoto-allow
exemption, case-insensitivity, and the PreToolUse-only / empty-text guards.
"""
from __future__ import annotations
import importlib
import pytest
from makoto.schema import PreCheck

MOD = importlib.import_module("makoto.prechecks.precheck_1_34")
PAT = PreCheck(id="1.34", fire_level="error",
              description="illusory Claude-authorship trailer", retry_hint="remove it")

# makoto-allow: test fixtures must carry the literal trailer to exercise the detector
_TRAILER = "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"


def _bash(command: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}}


def _write(content: str, file_path: str = "notes.md") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content}}


def _fire(evt: dict):
    return MOD.predicate(current_event=evt, history=[], pattern=PAT)


# --- TP: it fires at both creation points -----------------------------------
def test_fires_on_git_commit_command():
    cmd = f'git commit -m "$(cat <<EOF\nfeat: x\n\n{_TRAILER}\nEOF\n)"'
    f = _fire(_bash(cmd))
    assert f is not None and f.pattern_id == "1.34"


def test_fires_on_written_content():
    f = _fire(_write(f"# Changelog\n\n{_TRAILER}\n"))
    assert f is not None and f.line == 3


def test_fires_case_insensitive_github_casing():
    # git/GitHub emit the lowercase-keyword form
    f = _fire(_bash('git commit -m "x\n\nCo-authored-by: Claude <noreply@anthropic.com>"'))
    assert f is not None


def test_fires_on_edit_new_string():
    evt = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
           "tool_input": {"file_path": "x.md", "new_string": _TRAILER}}
    assert _fire(evt) is not None


# --- TN: it stays silent where it must --------------------------------------
def test_human_coauthor_passes():
    # a genuine human co-author is NOT an illusory authorship claim
    f = _fire(_bash('git commit -m "x\n\nCo-authored-by: Jane Doe <jane@example.com>"'))
    assert f is None


def test_makoto_allow_exempts():
    content = f"{_TRAILER}\n# makoto-allow: documenting the policy verbatim"
    assert _fire(_write(content)) is None


def test_unrelated_content_silent():
    assert _fire(_bash('git commit -m "fix: unrelated, no trailer"')) is None
    assert _fire(_write("def f():\n    return 1\n")) is None


def test_non_pretooluse_silent():
    evt = {"hook_event_name": "Stop", "tool_name": "Bash",
           "tool_input": {"command": _TRAILER}}
    assert _fire(evt) is None


def test_empty_input_silent():
    assert _fire({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                  "tool_input": {}}) is None
