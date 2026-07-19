"""Cross-machine world resolution for the Stop-gate fs closures (issue #2).

gate.completion verifies a production claim against the results ledger and a cwd-relative
os.path.exists. That observation window has a measured blind spot (FP, 2026-07-16): a file
produced on a REMOTE machine over ssh and landed locally via `git pull` IS on disk — but under
a repo root, not under cwd, and a bare-name claim ("index.md") resolves to <cwd>/index.md and
misses. The claim was true; the world just wasn't looked at where it lives.

This module WIDENS THE OBSERVATION, never the verdict:

  - candidate roots are ONLY local git work-trees this session actually synced — a
    `git -C <dir> pull|fetch` or `cd <dir> && git pull|fetch` Bash event (bounded regex over
    session history; no os.walk, per the Stop-hot-path rule in _dispatch);
  - a candidate file must be git-TRACKED in that root (`git ls-files` — an index query, not a
    filesystem crawl) AND suffix-match the claim at a path-separator boundary (the fakeexcuse
    firewall from substrate._shared: auth.py never matches auth_helper.py) AND exist on disk
    right now.

A claim about a file that exists nowhere still blocks: every path out of this module ends in a
live os.path.exists on a tracked file. Falsifiability is preserved — the check sees more of the
world; it does not believe more of the word.

Deliberate non-goal: commands inside an `ssh <host> '...'` string can match the cd-form and
yield a REMOTE path. Harmless by construction — the path only survives if it is ALSO a local
git work-tree holding a tracked, existing file, which in the dual-machine mirror layout is
exactly the synced-clone case this patch exists to recognize.
"""
from __future__ import annotations
import os
import re
import subprocess
from makoto.substrate._shared import _path_components, _suffix_match
from makoto.substrate.io import iter_tool_events

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

    Sources are the session's own Bash events (the faithful events-table rows, same feed the
    fabrication gates walk) — a dir qualifies only if the agent actually ran a pull/fetch
    against it AND it exists locally as a git work-tree. Fail-open per event: an unparseable
    row is skipped by iter_tool_events; a vanished dir is skipped here."""
    roots, seen = [], set()
    for tool, cmd, _resp in iter_tool_events(history):
        if len(roots) >= cap:
            break
        if (tool or "") != "Bash" or not cmd:
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
    return roots[:cap]


def resolve_in_synced_repos(loc, roots):
    """The absolute path of a tracked file in one of `roots` that suffix-matches `loc` at a
    separator boundary and exists on disk — else None (caller falls back to its original
    verdict; resolution failure never discharges anything)."""
    comps = _path_components(loc)
    if not comps or not roots:
        return None
    base = comps[-1]
    if not base or base in (".", ".."):
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
                full = os.path.join(root, rel)
                if os.path.exists(full):
                    return full
        except Exception:
            continue
    return None
