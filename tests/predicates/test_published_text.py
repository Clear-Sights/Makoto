"""content.illusory_authorship_trailer reads what a GitHub MCP call publishes, and nothing else."""
from __future__ import annotations

import pytest

from makoto.checks import illusoryAuthorshipTrailer as mod

FOOTER = "\U0001f916 Gener" + "ated with [Claude Code](https://claude.com/claude-code)"
TRAILER = "Co-Author" + "ed-By: Claude <x@y>"


def _fires(tool, tool_input):
    ev = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    return mod.predicate(current_event=ev, history=[], pattern=mod.CHECK)


@pytest.mark.parametrize("tool,ti", [
    ("mcp__github__create_pull_request", {"title": "t", "body": f"Before: x\n\n{FOOTER}"}),
    ("mcp__github__add_issue_comment", {"body": FOOTER}),
    ("mcp__github__merge_pull_request", {"commit_message": TRAILER}),
    ("mcp__github__create_or_update_file", {"content": "x", "message": f"m\n\n{TRAILER}"}),
    ("mcp__github__push_files", {"message": "m", "files": [{"path": "a", "content": TRAILER}]}),
])
def test_published_attribution_fires(tool, ti):
    assert _fires(tool, ti) is not None


@pytest.mark.parametrize("tool,ti", [
    ("mcp__github__create_pull_request", {"title": "t", "body": "Before: x\n\nAfter: y"}),
    ("mcp__github__search_commits", {"query": TRAILER}),
    ("mcp__hearthbot__reply", {"text": FOOTER}),
])
def test_unpublished_or_clean_is_silent(tool, ti):
    assert _fires(tool, ti) is None
