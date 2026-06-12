"""shared pytest fixtures for makoto test suite.

Scope: only the dedup-clear-win fixtures. Speculative history-builder fixtures
(Read/Bash/TodoWrite entries) are intentionally NOT added here — they should be
introduced when v1.1 predicate tests reveal their concrete shape, not pre-abstracted.

Provides:
  evt(file_path, content, event="PreToolUse", tool_name=None) -> dict
  stop_evt(message="", session_id="s") -> dict
  loaded_pattern(pid) -> PreCheck  (loads from real patterns.toml by id)
"""
from __future__ import annotations
import pytest
from pathlib import Path

from makoto.schema import PreCheck, load_prechecks


@pytest.fixture
def evt():
    """build a minimal PreToolUse (or override-event) payload."""
    def _evt(file_path: str = "", content: str = "",
             event: str = "PreToolUse", tool_name: str = ""):
        return {
            "hook_event_name": event,
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path, "content": content},
        }
    return _evt


@pytest.fixture
def stop_evt():
    """build a minimal Stop payload with optional response text + session id."""
    def _stop(message: str = "", session_id: str = "s") -> dict:
        return {
            "hook_event_name": "Stop",
            "session_id": session_id,
            "stop_reason": "end_turn",
            "response": message,
        }
    return _stop


@pytest.fixture
def loaded_pattern():
    """load a PreCheck from the live patterns.toml by id; raises if id is unknown.

    Use this instead of hand-constructing PreCheck dataclasses in tests, so test
    fixtures stay in sync with the live catalog (description / retry_hint /
    fire_level / keywords drift between test and prod is caught automatically).
    """
    patterns_path = Path(__file__).parent.parent / "data" / "patterns.toml"
    catalog = {p.id: p for p in load_prechecks(patterns_path)}

    def _by_id(pid: str) -> PreCheck:
        if pid not in catalog:
            raise KeyError(f"unknown pattern id {pid!r} (available: {sorted(catalog)})")
        return catalog[pid]
    return _by_id
