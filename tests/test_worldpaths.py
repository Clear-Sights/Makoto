"""Pin cross-machine and cross-process world resolution in checks/_worldpaths.py.

The pure helpers and end-to-end dispatch cases pin the governing law: widen OBSERVATION only,
never the verdict. A claim about a file/ref absent from the world must still block.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

from makoto.checks._worldpaths import (
    pushed_ref_matches_world,
    resolve_in_synced_repos,
    resolve_in_worktree,
    synced_repo_roots,
)


# ---- shared git-fixture + history-row helpers ----------------------------------------------
def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _make_repo(root: Path, files: dict) -> Path:
    """Init a real git repo at `root`, add+commit every path in `files` (rel -> content)."""
    root.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=root)
    _git("config", "user.email", "t@example.com", cwd=root)
    _git("config", "user.name", "T", cwd=root)
    _git("config", "commit.gpgsign", "false", cwd=root)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        _git("add", rel, cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)
    return root


def _bash_row(command: str) -> dict:
    """A minimal history row iter_tool_events can decode: a dict with a 'payload' key."""
    return {"payload": json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})}


# ==== cross-process local world facts =========================================================
def test_resolve_in_worktree_finds_untracked_repo_relative_artifact_from_nested_cwd(tmp_path):
    repo = _make_repo(tmp_path / "repo", {"seed.txt": "seed\n"})
    nested = repo / "work"
    nested.mkdir()
    artifact = repo / ".claude" / "skills" / "check_installed.py"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("print('RED')\n", encoding="utf-8")
    assert resolve_in_worktree(".claude/skills/check_installed.py", nested) == str(artifact)


def test_resolve_in_worktree_preserves_absence_and_root_confinement(tmp_path):
    repo = _make_repo(tmp_path / "repo", {"seed.txt": "seed\n"})
    nested = repo / "work"
    nested.mkdir()
    (tmp_path / "outside.py").write_text("outside\n", encoding="utf-8")
    assert resolve_in_worktree("genuinely_absent.py", nested) is None
    assert resolve_in_worktree("../outside.py", nested) is None


def test_pushed_ref_matches_world_requires_equal_local_and_origin_refs(tmp_path):
    repo = _make_repo(tmp_path / "repo", {"seed.txt": "seed\n"})
    oid = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()
    _git("update-ref", "refs/heads/topic/world", oid, cwd=repo)
    assert pushed_ref_matches_world("I've pushed it to topic/world.", repo) is False
    _git("update-ref", "refs/remotes/origin/topic/world", oid, cwd=repo)
    assert pushed_ref_matches_world("I've pushed it to topic/world.", repo) is True


# ==== synced_repo_roots =======================================================================
def test_synced_repo_roots_detects_git_dash_c_pull(tmp_path):
    repo = _make_repo(tmp_path / "Projects" / "wiki", {"index.md": "# hi\n"})
    roots = synced_repo_roots([_bash_row(f"git -C {repo} pull --ff-only")], str(tmp_path))
    assert str(repo) in roots


def test_synced_repo_roots_detects_cd_and_git_pull(tmp_path):
    repo = _make_repo(tmp_path / "Projects" / "wiki2", {"index.md": "# hi\n"})
    roots = synced_repo_roots([_bash_row(f"cd {repo} && git pull")], str(tmp_path))
    assert str(repo) in roots


def test_synced_repo_roots_detects_fetch_too(tmp_path):
    repo = _make_repo(tmp_path / "Projects" / "wiki3", {"index.md": "# hi\n"})
    roots = synced_repo_roots([_bash_row(f"git -C {repo} fetch")], str(tmp_path))
    assert str(repo) in roots


def test_synced_repo_roots_handles_quoted_path_with_spaces(tmp_path):
    repo = _make_repo(tmp_path / "My Projects" / "wiki", {"index.md": "hi\n"})
    roots = synced_repo_roots([_bash_row(f'git -C "{repo}" pull')], str(tmp_path))
    assert str(repo) in roots


def test_synced_repo_roots_ignores_non_git_dir(tmp_path):
    plain = tmp_path / "not_a_repo"
    plain.mkdir()
    roots = synced_repo_roots([_bash_row(f"git -C {plain} pull")], str(tmp_path))
    assert str(plain) not in roots


def test_synced_repo_roots_ignores_non_bash_events(tmp_path):
    repo = _make_repo(tmp_path / "Projects" / "wiki4", {"index.md": "hi\n"})
    row = {"payload": json.dumps({"tool_name": "Write",
                                   "tool_input": {"command": f"git -C {repo} pull"}})}
    assert synced_repo_roots([row], str(tmp_path)) == []


def test_synced_repo_roots_ignores_plain_git_status(tmp_path):
    repo = _make_repo(tmp_path / "Projects" / "wiki5", {"index.md": "hi\n"})
    roots = synced_repo_roots([_bash_row(f"git -C {repo} status")], str(tmp_path))
    assert str(repo) not in roots


# ==== resolve_in_synced_repos =================================================================
def test_resolve_bare_name_match(tmp_path):
    repo = _make_repo(tmp_path / "wiki", {"index.md": "# Index\n"})
    assert resolve_in_synced_repos("index.md", [str(repo)]) == str(repo / "index.md")


def test_resolve_nested_bare_name_match(tmp_path):
    repo = _make_repo(tmp_path / "wiki", {"docs/index.md": "# Index\n"})
    assert resolve_in_synced_repos("index.md", [str(repo)]) == str(repo / "docs" / "index.md")


def test_resolve_suffix_boundary_firewall_rejects_glob_overmatch(tmp_path):
    """'index.md' must never resolve against a tracked 'zindex.md' (git pathspec glob over-match)."""
    repo = _make_repo(tmp_path / "wiki", {"zindex.md": "decoy\n"})
    assert resolve_in_synced_repos("index.md", [str(repo)]) is None


def test_resolve_suffix_boundary_firewall_auth_py_vs_auth_helper_py(tmp_path):
    repo = _make_repo(tmp_path / "repo", {"auth_helper.py": "x = 1\n"})
    assert resolve_in_synced_repos("auth.py", [str(repo)]) is None


def test_resolve_untracked_file_stays_unresolved(tmp_path):
    """Present on disk but never `git add`ed -- git ls-files won't see it, so it can't discharge."""
    repo = _make_repo(tmp_path / "repo", {"index.md": "tracked\n"})
    (repo / "scratch.md").write_text("untracked\n")
    assert resolve_in_synced_repos("scratch.md", [str(repo)]) is None


def test_resolve_tracked_but_deleted_from_disk_stays_unresolved(tmp_path):
    """Tracked in git, but the working-tree file is gone -- the live os.path.exists still gates it."""
    repo = _make_repo(tmp_path / "repo", {"gone.md": "bye\n"})
    (repo / "gone.md").unlink()
    assert resolve_in_synced_repos("gone.md", [str(repo)]) is None


def test_resolve_nonexistent_claim_returns_none(tmp_path):
    repo = _make_repo(tmp_path / "repo", {"index.md": "hi\n"})
    assert resolve_in_synced_repos("totally_absent.md", [str(repo)]) is None


def test_resolve_no_roots_returns_none():
    assert resolve_in_synced_repos("index.md", []) is None


# ==== end-to-end dispatch: the actual issue #2 repro + controls ==============================
def _setup_state(tmp_path):
    from makoto.record.db import init_db
    state_dir = tmp_path / "makoto_state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("Smith 2020\n")
    init_db(state_dir, citations)
    return state_dir


def _run_dispatch(state_dir, payload: dict, extra_env: dict | None = None) -> tuple[int, str]:
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    return proc.returncode, proc.stdout.decode("utf-8")


def test_dispatch_completion_gate_discharges_via_synced_repo_after_remote_git_pull(tmp_path):
    """The issue #2 repro: index.md was produced on a REMOTE machine (ssh) and landed here via
    a local `git pull` -- it lives under a repo root, not under cwd. The claim is TRUE; the
    gate must not false-block it."""
    state_dir = _setup_state(tmp_path)
    sid = "worldpaths_fp"
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    repo = _make_repo(tmp_path / "Projects" / "wiki", {"index.md": "# Index\npage count: 42\n"})

    pull = {
        "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
        "cwd": str(cwd),
        "tool_input": {"command": f"git -C {repo} pull --ff-only"},
        "tool_response": {"stdout": "Already up to date.", "stderr": "", "exitCode": 0},
    }
    rc, _ = _run_dispatch(state_dir, pull)
    assert rc == 0

    stop = {
        "hook_event_name": "Stop", "session_id": sid, "cwd": str(cwd),
        "last_assistant_message": "Done — updated index.md with the new page counts.",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", f"file lives under the synced repo root; claim is true, must not block: {out}"


def test_dispatch_completion_gate_still_blocks_without_a_synced_pull(tmp_path):
    """Control: SAME claim, SAME file layout, but no git-pull Bash event ever ran in this
    session -- the fix must not become a blanket allow. The gate still blocks by default."""
    state_dir = _setup_state(tmp_path)
    sid = "worldpaths_control"
    cwd = tmp_path / "workspace2"
    cwd.mkdir()
    _make_repo(tmp_path / "Projects" / "wiki2", {"index.md": "# Index\n"})  # exists, never synced

    stop = {
        "hook_event_name": "Stop", "session_id": sid, "cwd": str(cwd),
        "last_assistant_message": "Done — updated index.md with the new page counts.",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "no git-pull event ever synced this repo -- must still block"
    assert json.loads(out)["decision"] == "block"


def test_dispatch_completion_gate_still_blocks_on_genuinely_absent_file(tmp_path):
    """A synced repo root IS present in history, but the claimed file exists nowhere in it --
    falsifiability must be preserved: the fix widens observation, it never rubber-stamps the
    verdict. Every alternate path still ends in a live existence check."""
    state_dir = _setup_state(tmp_path)
    sid = "worldpaths_absent"
    cwd = tmp_path / "workspace3"
    cwd.mkdir()
    repo = _make_repo(tmp_path / "Projects" / "wiki3", {"index.md": "# Index\n"})

    pull = {
        "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
        "cwd": str(cwd),
        "tool_input": {"command": f"git -C {repo} pull --ff-only"},
        "tool_response": {"stdout": "Already up to date.", "stderr": "", "exitCode": 0},
    }
    rc, _ = _run_dispatch(state_dir, pull)
    assert rc == 0

    stop = {
        "hook_event_name": "Stop", "session_id": sid, "cwd": str(cwd),
        "last_assistant_message": "Done - added rate limiting to src/nonexistent_zzz.py",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out, "the claimed file exists nowhere -- must still block"
    assert json.loads(out)["decision"] == "block"


def test_dispatch_completion_gate_discharges_via_cd_and_pull_form(tmp_path):
    """Same FP repro, but the session used the `cd <dir> && git pull` shell form instead of
    `git -C <dir> pull` -- both forms must resolve identically."""
    state_dir = _setup_state(tmp_path)
    sid = "worldpaths_cdform"
    cwd = tmp_path / "workspace4"
    cwd.mkdir()
    repo = _make_repo(tmp_path / "Projects" / "wiki4", {"index.md": "# Index\n"})

    pull = {
        "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
        "cwd": str(cwd),
        "tool_input": {"command": f"cd {repo} && git pull --ff-only"},
        "tool_response": {"stdout": "Already up to date.", "stderr": "", "exitCode": 0},
    }
    rc, _ = _run_dispatch(state_dir, pull)
    assert rc == 0

    stop = {
        "hook_event_name": "Stop", "session_id": sid, "cwd": str(cwd),
        "last_assistant_message": "Done — updated index.md with the new page counts.",
    }
    rc, out = _run_dispatch(state_dir, stop)
    assert rc == 0
    assert out == "", f"cd-form pull must resolve exactly like -C form: {out}"
