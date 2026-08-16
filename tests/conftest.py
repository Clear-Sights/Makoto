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

from makoto.substrate._loader import load_precheck_catalog


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
    """load a Check from the live checks/ catalog by id; raises if id is unknown.

    Use this instead of hand-constructing PreCheck dataclasses in tests, so test
    fixtures stay in sync with the live catalog (description / retry_hint /
    posture / keywords drift between test and prod is caught automatically).

    2026-08-16: sourced from `substrate._loader.load_precheck_catalog()` (`schema.load_prechecks()`
    -- the TOML/loader-adapter shim -- was retired once its callers finished migrating). Returns
    `Check` instances now, not `PreCheck`; the return annotation is documentation, not enforced.
    """
    catalog = {c.id: c for c in load_precheck_catalog()}

    def _by_id(pid: str):
        if pid not in catalog:
            raise KeyError(f"unknown pattern id {pid!r} (available: {sorted(catalog)})")
        return catalog[pid]
    return _by_id
