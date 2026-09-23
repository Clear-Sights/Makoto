"""makoto.checks.claudeIdentity -- gate.claude_identity, register entry
`A13 SETTING CALLED INHERENT`.

A commit is about to be stamped with an identity nobody chose: the container's git layer (an
env var or a config file) names Claude at the anthropic.com noreply address, and a plain
`git commit` takes that setting as if it were who is writing. content.illusory_authorship_trailer
reads the text a call introduces, so it never sees this: the author field is written from the
git layer, not from the command. Measured 2026-09-23 over 17 trees: 834 commits authored this
way, 0 caught.

The entry's fix is to name which layer set the value and where it changes, and that is a
reading makoto can take before the write: `git var GIT_AUTHOR_IDENT` / `GIT_COMMITTER_IDENT`
run with the command's own overrides (leading `VAR=`, `env -u`, `export`/`unset`, `git -c`,
`-C`, `cd`, `--author=`) is what git itself will stamp.

Two edges, one reading. Upstream: a commit-creating git command whose author or committer
resolves to Claude is refused before it runs. Damage control: a `git push` whose outgoing
commits (not on any remote-tracking ref) carry one is refused before anything leaves the
machine, which catches commits made where the first edge never looked (a script, a hook-less
session). Any git failure reads as no finding: this gate fails open.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Optional

from makoto.core._shell import _shell_segments
from makoto.vocab import Finding

# Claude at the anthropic.com noreply address, and claude[bot] at its users.noreply.github.com
# address, are the two forms on the trees. A human named Claude with their own address passes.
_CLAUDE_IDENT_RX = re.compile(r"@anthropic\.com>|claude\[bot\]", re.I)
_COMMITTING = frozenset({"commit", "merge", "pull", "cherry-pick", "revert", "am", "rebase"})
_ASSIGN_RX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _git(args: list, cwd: str, env: dict) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _split_env(argv: list, env: dict) -> tuple[list, dict]:
    """Peel leading `VAR=val` words and an `env [-u VAR] [VAR=val]` wrapper off one command."""
    env = dict(env)
    i = 0
    while i < len(argv) and _ASSIGN_RX.match(argv[i]):
        k, v = argv[i].split("=", 1)
        env[k] = v
        i += 1
    if i < len(argv) and os.path.basename(argv[i]) == "env":
        i += 1
        while i < len(argv):
            if argv[i] in ("-u", "--unset") and i + 1 < len(argv):
                env.pop(argv[i + 1], None)
                i += 2
            elif _ASSIGN_RX.match(argv[i]):
                k, v = argv[i].split("=", 1)
                env[k] = v
                i += 1
            else:
                break
    return argv[i:], env


def _git_parts(argv: list) -> Optional[tuple[list, str, list]]:
    """(global options to replay, subcommand, its arguments) for a `git ...` argv, else None."""
    if not argv or os.path.basename(argv[0]) != "git":
        return None
    glob, i = [], 1
    while i < len(argv) and argv[i].startswith("-"):
        if argv[i] in ("-C", "-c") and i + 1 < len(argv):
            glob += argv[i:i + 2]
            i += 2
        else:
            i += 1
    return (glob, argv[i], argv[i + 1:]) if i < len(argv) else None


def _layer(key: str, var: str, glob: list, cwd: str, env: dict) -> str:
    """Which layer set `key` (user.email): the env var, a `git -c`, or a config file."""
    if var in env:
        return f"env {var}"
    if any(g.startswith(f"{key}=") for g in glob):
        return f"git -c {key}"
    out = _git([*glob, "config", "--show-origin", "--get", key], cwd, env)
    return out.split("\t", 1)[0] if out else "git default"


def _commit_finding(glob, sub, args, cwd, env) -> Optional[str]:
    if sub in ("merge", "pull") and "--ff-only" in args:
        return None
    if _git([*glob, "rev-parse", "--git-dir"], cwd, env) is None:
        return None  # not the repo the command will run in: its local config is unread
    author = next((a.split("=", 1)[1] for a in args if a.startswith("--author=")), None)
    for role, var in (("author", "GIT_AUTHOR_IDENT"), ("committer", "GIT_COMMITTER_IDENT")):
        if role == "author" and author is not None:
            ident = author
        else:
            ident = _git([*glob, "var", var], cwd, env)
            if ident is None:
                return None
        if _CLAUDE_IDENT_RX.search(ident):
            where = ("--author" if role == "author" and author is not None
                     else _layer("user.email", f"GIT_{role.upper()}_EMAIL", glob, cwd, env))
            name = re.sub(r">.*", ">", ident.strip())
            return f"`git {sub}` would record {role} {name}, set by {where}"
    return None


def _push_finding(glob, args, cwd, env) -> Optional[str]:
    pos = [a for a in args if not a.startswith("-")]
    if "--all" in args or "--mirror" in args:
        revs = ["--branches"]
    else:
        revs = [r.lstrip("+").split(":", 1)[0] for r in pos[1:]]
        revs = [r for r in revs if r] or (["HEAD"] if not pos[1:] else [])
    if not revs:
        return None
    out = _git([*glob, "log", "-n", "500", "--format=%h%x00%an <%ae>%x00%cn <%ce>", *revs,
                "--not", "--remotes"], cwd, env)
    bad = [ln.split("\0") for ln in (out or "").splitlines() if _CLAUDE_IDENT_RX.search(ln)]
    if not bad:
        return None
    who = bad[0][1] if _CLAUDE_IDENT_RX.search(bad[0][1]) else bad[0][2]
    return (f"`git push` would publish {len(bad)} commit(s) authored or committed as Claude, "
            f"first {bad[0][0]} ({who})")


def predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional[Finding]:
    if current_event.get("tool_name") != "Bash":
        return None
    cmd = (current_event.get("tool_input") or {}).get("command", "") or ""
    cwd = current_event.get("cwd") or os.getcwd()
    env = dict(os.environ)
    for argv, _ in _shell_segments(cmd):
        argv, seg_env = _split_env(argv, env)
        if not argv:
            env = seg_env  # a bare `VAR=val` line sets the shell's own variable
            continue
        head = argv[0]
        if head == "cd" and len(argv) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(argv[1]))
            continue
        if head == "export":
            env.update(a.split("=", 1) for a in argv[1:] if "=" in a)
            continue
        if head == "unset":
            for a in argv[1:]:
                env.pop(a, None)
            continue
        parts = _git_parts(argv)
        if parts is None:
            continue
        glob, sub, args = parts
        msg = (_commit_finding(glob, sub, args, cwd, seg_env) if sub in _COMMITTING
               else _push_finding(glob, args, cwd, seg_env) if sub == "push" else None)
        if msg:
            return Finding(pattern_id=pattern.id, file="Bash command", line=1, level="error",
                           message=f"row {pattern.id}: {msg}", retry_hint=pattern.retry_hint,
                           snippet=" ".join(argv)[:200])
    return None


from makoto.registry import Check as _Check
RETRY_HINT = ("Commit as the human, not the container: unset GIT_AUTHOR_*/GIT_COMMITTER_* "
              "(`env -u`) and pass `-c user.name=... -c user.email=...`; re-author unpushed "
              "commits before pushing.")
DESCRIPTION = "a commit or push that records Claude as author or committer from the git layer"
CHECK = _Check(id="gate.claude_identity", applies_at="Pre", posture="BLOCK",
               predicate_module=__name__, keywords=("git",), retry_hint=RETRY_HINT,
               description=DESCRIPTION, tests="LIVE_QUERY",
               eats=frozenset({"current_event", "pattern"}))
