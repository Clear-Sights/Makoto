"""tests for makoto/state.py — _state_dir() resolution."""
import os
from pathlib import Path


def test_state_dir_defaults_to_claude_home(monkeypatch):
    """no env var -> ~/.claude/makoto_state/."""
    from makoto.state import _state_dir
    monkeypatch.delenv("MAKOTO_STATE_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path("/fake/home"))
    assert _state_dir() == Path("/fake/home/.claude/makoto_state")


def test_state_dir_honors_env_var(monkeypatch):
    """MAKOTO_STATE_DIR env var overrides default."""
    from makoto.state import _state_dir
    monkeypatch.setenv("MAKOTO_STATE_DIR", "/custom/state/dir")
    assert _state_dir() == Path("/custom/state/dir")
