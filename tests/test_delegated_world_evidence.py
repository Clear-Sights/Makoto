"""Cross-process world evidence must outrank gaps in recorded tool history.

Each false-positive reproducer is paired with the fabrication control for the same gate.  The
controls are the teeth: widening observation must never become blanket belief.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys

from makoto._dispatch import run_stop_checks


_COMMIT_DDL = (
    "CREATE TABLE commitments (commitment_key TEXT PRIMARY KEY, session_id TEXT, "
    "location TEXT, qty_min REAL, qty_max REAL, status TEXT NOT NULL DEFAULT 'open', "
    "retract_param TEXT, created_event_id INTEGER, ts TEXT)"
)
_LEDGER_DDL = (
    "CREATE TABLE ledger (key TEXT PRIMARY KEY, value TEXT, kind TEXT NOT NULL, "
    "exit INTEGER, source_event_id INTEGER, session_id TEXT, ts TEXT)"
)


def _conn():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute(_COMMIT_DDL)
    conn.execute(_LEDGER_DDL)
    return conn


def _git(repo, *args, input_text=None):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Makoto Test",
        "GIT_AUTHOR_EMAIL": "makoto@example.invalid",
        "GIT_COMMITTER_NAME": "Makoto Test",
        "GIT_COMMITTER_EMAIL": "makoto@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=input_text, text=True,
        check=True, capture_output=True, env=env,
    ).stdout.strip()


def _repo_with_ref(tmp_path, *, remote_matches=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    tree = _git(repo, "write-tree")
    local_oid = _git(repo, "commit-tree", tree, input_text="local\n")
    _git(repo, "update-ref", "refs/heads/main", local_oid)
    remote_oid = local_oid
    if not remote_matches:
        remote_oid = _git(repo, "commit-tree", tree, input_text="elsewhere\n")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", f"{remote_oid}:refs/heads/main")
    return repo


def _messages(cwd, text, history=()):
    conn = _conn()
    try:
        findings = run_stop_checks(conn, {
            "hook_event_name": "Stop",
            "last_assistant_message": text,
            "session_id": "delegated-world",
            "cwd": str(cwd),
        }, history)
    finally:
        conn.close()
    return {f.pattern_id: f.message for f in findings}


def test_fp_direct_remote_ref_matches_with_empty_history(tmp_path):
    """A direct same-repository/ref/tip observation certifies without a transcript proxy."""
    repo = _repo_with_ref(tmp_path)
    messages = _messages(repo, "I've pushed it to main.", history=[])
    assert "gate.claimed_shipped" not in messages, messages


def test_direct_remote_ref_mismatch_contradicts_push_claim(tmp_path):
    repo = _repo_with_ref(tmp_path, remote_matches=False)
    messages = _messages(repo, "I've pushed it to main.", history=[])
    assert "gate.claimed_shipped" in messages, messages


def test_fp_subprocess_produced_repo_relative_file_with_empty_history(tmp_path):
    """Firing B: a child wrote the file at worktree root while Stop cwd is a nested directory."""
    repo = tmp_path / "repo"
    nested_cwd = repo / "work"
    nested_cwd.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    artifact = repo / ".claude" / "skills" / "check_installed.py"
    subprocess.run(
        [sys.executable, "-c",
         "from pathlib import Path; p=Path(__import__('sys').argv[1]); "
         "p.parent.mkdir(parents=True); "
         "p.write_text('#!/usr/bin/env python3\\nprint(\"RED\")\\n'); p.chmod(0o755)",
         str(artifact)],
        check=True,
    )
    ran = subprocess.run([str(artifact)], check=True, capture_output=True, text=True)
    assert ran.stdout.strip() == "RED"
    messages = _messages(
        nested_cwd, "I produced .claude/skills/check_installed.py.", history=[],
    )
    assert "gate.completion" not in messages, messages


def test_tp_claimed_file_still_fires_when_genuinely_absent(tmp_path):
    repo = tmp_path / "repo"
    nested_cwd = repo / "work"
    nested_cwd.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    messages = _messages(
        nested_cwd, "I produced .claude/skills/check_installed.py.", history=[],
    )
    assert "gate.completion" in messages, messages
