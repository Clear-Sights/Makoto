"""shared state-directory resolution for the Makoto validator package.

Reads $MAKOTO_STATE_DIR env var; defaults to $HOME/.claude/makoto_state/.
Importable by _dispatch.py, refresh_citations.py, and tests without circular
imports (Knight-Leveson: stdlib only).
"""
from __future__ import annotations
import os
from pathlib import Path


def _state_dir() -> Path:
    """resolve the canonical state directory.

    $MAKOTO_STATE_DIR overrides; default $HOME/.claude/makoto_state/.
    """
    env = os.environ.get("MAKOTO_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "makoto_state"
