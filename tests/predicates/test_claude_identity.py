"""gate.claude_identity: red on each plant, silent on the commands that commit as the human."""
from __future__ import annotations

import os
import subprocess

import pytest

from makoto.checks import spec as mod

CLAUDE = {"GIT_AUTHOR_NAME": "Claude", "GIT_AUTHOR_EMAIL": "noreply" + "@anthropic.com",
          "GIT_COMMITTER_NAME": "Claude", "GIT_COMMITTER_EMAIL": "noreply" + "@anthropic.com"}
HUMAN = "-c user.name=Ann -c user.email=ann@example.org"
UNSET = "env -u GIT_AUTHOR_NAME -u GIT_AUTHOR_EMAIL -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL"


def _run(cmd, cwd, env):
    subprocess.run(cmd, shell=True, cwd=cwd, env=env, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A clone with one pushed human commit; the container's env names Claude."""
    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1", **CLAUDE}
    for k in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(k)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    _run(f"git init -q --bare {origin} && git clone -q {origin} {work}", tmp_path, env)
    _run(f"{UNSET} git {HUMAN} commit -q --allow-empty -m one && git push -q origin HEAD",
         work, env)
    return work, env


def _fires(cmd, cwd):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)}
    return mod.identity_predicate(current_event=ev, history=[], pattern=mod.identity_CHECK)


@pytest.mark.parametrize("cmd", [
    "git commit -m x",                                      # the container's env layer
    "git commit --author='Ann <ann@example.org>' -m x",     # committer still Claude
    f"env -u GIT_AUTHOR_NAME -u GIT_AUTHOR_EMAIL git {HUMAN} commit -m x",  # committer env left
    "cd . && git merge topic",
    "# keel-guard: U08\ngit cherry-pick abc",
])
def test_commit_as_claude_fires(repo, cmd):
    work, _ = repo
    f = _fires(cmd, work)
    assert f is not None and "Claude" in f.message


def test_config_layer_is_named(repo, monkeypatch):
    work, env = repo
    _run("git config --global user.email noreply" + "@anthropic.com", work, env)
    # A name too: without one git takes it from the OS account, and where that is empty (the
    # CI runner's) `git var` fails, the commit would fail with it, and nothing fires.
    _run("git config --global user.name Someone", work, env)
    f = _fires(f"{UNSET} git commit -m x", work)
    assert f is not None and ".gitconfig" in f.message


@pytest.mark.parametrize("cmd", [
    f"{UNSET} git {HUMAN} commit -m x",
    f"GIT_AUTHOR_EMAIL=ann@example.org GIT_COMMITTER_EMAIL=ann@example.org git commit -m x",
    "export GIT_AUTHOR_EMAIL=a@b GIT_COMMITTER_EMAIL=a@b; git commit -m x",
    "unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL; "
    f"git {HUMAN} commit -m x",
    "GIT_AUTHOR_EMAIL=a@b\nGIT_COMMITTER_EMAIL=a@b\ngit commit -m x",
    "GIT_COMMITTER_EMAIL=ann@example.org git commit --author='Ann <ann@example.org>' -m x",
    "git merge --ff-only origin/main",
    "git log --author=claude",
    "git status && git diff",
    "echo git commit",
])
def test_commit_as_human_is_silent(repo, cmd):
    work, _ = repo
    assert _fires(cmd, work) is None


def test_push_of_claude_commit_fires_and_clean_push_is_silent(repo):
    work, env = repo
    assert _fires("git push -u origin HEAD", work) is None       # everything already on origin
    _run("git commit -q --allow-empty -m two", work, env)          # made where no hook looked
    for cmd, cwd in (("git push", work), ("git push origin HEAD:main", work),
                     (f"git -C {work} push --all", "/")):
        f = _fires(cmd, cwd)
        assert f is not None and "1 commit" in f.message, cmd
    assert _fires("git push origin :stale", work) is None          # a deletion publishes nothing


def test_not_a_repo_fails_open(tmp_path):
    assert _fires("git commit -m x", tmp_path) is None


def test_cd_moves_the_reading_into_the_repo(repo):
    work, _ = repo
    assert _fires(f"cd {work} && git commit -m x", "/") is not None
