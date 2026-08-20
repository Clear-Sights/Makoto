"""shared pytest fixtures for makoto test suite.

Scope: only the dedup-clear-win fixtures. Speculative history-builder fixtures
(Read/Bash/TodoWrite entries) are intentionally NOT added here — they should be
introduced when v1.1 predicate tests reveal their concrete shape, not pre-abstracted.

Provides:
  evt(file_path, content, event="PreToolUse", tool_name=None) -> dict
  stop_evt(message="", session_id="s") -> dict
  loaded_pattern(pid) -> PreCheck  (loads from real patterns.toml by id)
  state_dir(tmp_path) -> Path  (a real makoto state dir + CITATIONS.md, ready for init_db callers)
  run_dispatch(state_dir, payload, extra_env=None) -> (returncode, stdout)  (real `python -m
    makoto.dispatch` subprocess invocation)
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from makoto.registry import load_precheck_catalog


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

    2026-08-16: sourced from `registry.load_precheck_catalog()` (`schema.load_prechecks()`
    -- the TOML/loader-adapter shim -- was retired once its callers finished migrating). Returns
    `Check` instances now, not `PreCheck`; the return annotation is documentation, not enforced.
    """
    catalog = {c.id: c for c in load_precheck_catalog()}

    def _by_id(pid: str):
        if pid not in catalog:
            raise KeyError(f"unknown pattern id {pid!r} (available: {sorted(catalog)})")
        return catalog[pid]
    return _by_id


def _setup_state(tmp_path):
    """create a makoto.record.db with the 3 tables + minimal config; return state_dir."""
    from makoto.state.store import init_db
    state_dir = tmp_path / "makoto_state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n")
    init_db(state_dir, citations)
    return state_dir


@pytest.fixture
def state_dir(tmp_path):
    """a real makoto state dir (CITATIONS.md seeded, `init_db` already run). Plain-function
    twin `_setup_state` stays importable for cross-file callers that need it outside fixture
    injection (see tests/test_dispatch.py, tests/test_dispatch_posture_integration.py,
    tests/test_check_law_confluence.py)."""
    return _setup_state(tmp_path)


def _run_dispatch(state_dir, payload: dict, extra_env: dict | None = None) -> tuple[int, str]:
    """invoke `python -m makoto.dispatch` with payload on stdin; return (exit, stdout)."""
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto.dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent / "plugin"),
    )
    return proc.returncode, proc.stdout.decode("utf-8")


@pytest.fixture
def run_dispatch():
    """factory fixture: run_dispatch(state_dir, payload, extra_env=None) -> (returncode, stdout).
    Plain-function twin `_run_dispatch` stays importable for cross-file callers."""
    return _run_dispatch
