"""Cross-machine and cross-process world resolution for Stop gates.

gate.completion checks a claim against the results ledger and a cwd-relative os.path.exists,
which misses a file living under a synced repo root instead of cwd. This module WIDENS THE
OBSERVATION, never the verdict: every successful resolution still ends in a live
os.path.exists.

Candidate roots are only local git work-trees this session actually synced (a `git pull|fetch`
Bash event, bounded, no os.walk on the Stop hot path). A candidate file must be git-tracked in
that root and suffix-match the claim at a path-separator boundary (auth.py never matches
auth_helper.py).

Cross-process: a repo-relative artifact resolves from the local git worktree root and must
exist on disk now; a pushed-branch claim is backed only when the local branch and
`refs/remotes/origin/<branch>` point to the same object. No `git ls-remote` — network I/O does
not belong on the Stop hot path.

`substrate._shared` holds the cross-process implementations; re-exported here beside the
cross-machine resolver for one facade.

An `ssh <host> '...'` command can match the cd-form and yield a remote path; harmless since it
only survives if it is ALSO a local git work-tree with a tracked, existing file.
"""
from __future__ import annotations
import os
import re
import subprocess
from makoto.kit import _path_components, _suffix_match, iter_tool_events
# Facade re-export (see module docstring), not used below:
from makoto.kit import resolve_in_worktree

# `git -C <dir> pull|fetch` — the dir may be bare, or single/double quoted (spaces, CJK).
_GIT_C_RX = re.compile(
    r"""git\s+-C\s+(?:"([^"]+)"|'([^']+)'|(\S+))\s+(?:pull|fetch)\b""")
# `cd <dir> && git pull|fetch` (also after `;`) — same quoting forms.
_CD_GIT_RX = re.compile(
    r"""(?:^|&&|;)\s*cd\s+(?:"([^"]+)"|'([^']+)'|(\S+))\s*(?:&&|;)\s*git\s+(?:pull|fetch)\b""")

_ROOT_CAP = 8          # bounded: a Stop evaluates at most this many candidate roots
_LS_FILES_TIMEOUT = 3.0


def synced_repo_roots(history, cwd, cap=_ROOT_CAP):
    """Local git work-tree dirs this session synced, in first-seen order, capped.

    Only dirs the session actually ran pull/fetch against, that exist locally as a git
    work-tree. Fail-open per event: an unparseable row is skipped by iter_tool_events; a
    vanished dir is skipped here."""
    roots, seen = [], set()
    for tool, cmd, _resp in iter_tool_events(history):
        if len(roots) >= cap:
            break
        if tool != "Bash" or not cmd:
            continue
        for rx in (_GIT_C_RX, _CD_GIT_RX):
            for m in rx.finditer(cmd):
                d = next(g for g in m.groups() if g)
                d = os.path.expanduser(d)
                if not os.path.isabs(d):
                    d = os.path.join(cwd or "", d)
                d = os.path.normpath(d)
                if d in seen:
                    continue
                seen.add(d)
                try:
                    if os.path.isdir(os.path.join(d, ".git")):
                        roots.append(d)
                except Exception:
                    continue
    return roots[:cap]           # one event can append several roots past the top-of-loop break


def resolve_in_synced_repos(loc, roots):
    """Absolute path of a tracked file in `roots` that suffix-matches `loc` at a separator
    boundary and exists on disk, else None."""
    comps = _path_components(loc)
    if not comps or not roots:
        return None
    base = comps[-1]
    if base in (".", ".."):
        return None
    for root in roots:
        try:
            out = subprocess.run(
                ["git", "-C", root, "ls-files", "-z", "--", f"*{base}", base],
                capture_output=True, timeout=_LS_FILES_TIMEOUT)
            if out.returncode != 0:
                continue
            for rel in out.stdout.decode("utf-8", "replace").split("\0"):
                if not rel:
                    continue
                if not _suffix_match(comps, _path_components(rel)):
                    continue          # glob over-match (zindex.md for index.md) — firewall holds
                full = os.path.normpath(os.path.join(root, rel))
                if os.path.isfile(full):
                    return full
        except Exception:
            continue
    return None
