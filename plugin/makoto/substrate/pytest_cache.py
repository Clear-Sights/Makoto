"""makoto.substrate.pytest_cache (L1) — existence-filtered reader over pytest's own on-disk record.

ACCESS CONTRACT: deterministic direct-pointer I/O only. The record is found by walking UP from
the session's cwd to the nearest ancestor holding `.pytest_cache/v/cache/lastfailed` (pytest
writes its cache at the rootdir, and a session often sits in a subdirectory of it), stopping at
the first ancestor that is a git work-tree root: another project's record is never read. Then
only paths NAMED INSIDE the record are followed, each scanned for the node's own concrete tokens
(a line-leading `def <test_name>`, plus `class <Name>` for each class segment). Every entry is
examined; each pointed file is read at most once. O(entries + depth), zero directory
enumeration — no enumeration primitive of any kind, ever (pinned by tests/test_pytest_cache.py).

WHY existence-filtering (the staleness firewall): pytest clears a lastfailed entry only when it
COLLECTS that node and sees it pass — a deleted/renamed node is uncollectable, so its entry
persists forever. A surviving entry therefore means: this node EXISTS and its last recorded run
FAILED, never re-run green — pytest rewrites the cache on every run, so the record is
latest-wins with no makoto bookkeeping. stdlib json/re/os only.
"""
from __future__ import annotations
from makoto.vocab import _lazy_re
import json
import os
import re

# Hot-path bound (literal-lookup latency contract: the WHOLE lookup is a literal
# direct-pointer read and must stay far under ~200-300ms): read at most _MAX_READ_BYTES per
# pointed file, each file once however many entries name it. Past-cap bytes are UNEXAMINED ->
# fail-open, never a crawl. There is no entry cap: a cap let deleted-test entries that sort
# first hide the one live failing node behind them (register H2).
_MAX_READ_BYTES = 256 * 1024
_NAME_RX = _lazy_re(r"[A-Za-z_]\w*\Z")


def _node_exists(cwd: str, node: str, _files=None) -> bool:
    """Does lastfailed node-id `node` still exist on disk under `cwd`? Direct pointer:
    the node carries its own path; for `file::(Class::)*name` the parametrize `[...]` id is
    stripped, the FINAL segment must appear as a line-leading `def <name>` and every
    intermediate segment as a line-leading `class <Class>` in that file's text — a
    commented-out or string-embedded token, or a method whose class was renamed away, is
    NOT a live node (pytest cannot collect it, so its entry can never clear). Absolute or
    parent-escaping paths (either separator) and symlinks resolving outside `cwd` are
    rejected (cross-project firewall); an unparseable name or unreadable file -> False
    (fail-open: the gate stays silent)."""
    parts = node.split("::")
    rel = parts[0]
    if not rel or os.path.isabs(rel) or rel.startswith("\\") or ".." in re.split(r"[/\\]", rel):
        return False
    path = os.path.join(cwd, rel)
    if not os.path.isfile(path):
        return False
    # Firewall, symlink half: a link inside cwd pointing outside it is another project's file.
    real_cwd = os.path.realpath(cwd)
    if not os.path.realpath(path).startswith(real_cwd.rstrip(os.sep) + os.sep):
        return False
    if len(parts) == 1:
        return True                        # module-level entry (collection error) -> file is the node
    # Strip the parametrize id from the WHOLE node before re-splitting: a `::` inside the
    # `[...]` id (parametrize over strings) must not displace the final segment. The scan
    # starts after `rel` so a literal `[` in the path itself cannot truncate it.
    cut = node.find("[", len(rel))
    parts = (node[:cut] if cut != -1 else node).split("::")
    name = parts[-1]
    if not _NAME_RX.match(name):
        return False
    src = (_files or {}).get(path)
    if src is None:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                src = f.read(_MAX_READ_BYTES)
        except OSError:
            return False
        if _files is not None:
            _files[path] = src
    for cls in parts[1:-1]:
        if not _NAME_RX.match(cls):
            return False
        if not re.search(rf"(?m)^[ \t]*class[ \t]+{re.escape(cls)}\b", src):
            return False
    return bool(re.search(rf"(?m)^[ \t]*(?:async[ \t]+)?def[ \t]+{re.escape(name)}\b", src))


def record_root(cwd: str) -> str | None:
    """The directory whose `.pytest_cache` holds pytest's record for a session at `cwd`: `cwd`
    itself or its nearest ancestor with a lastfailed file, never past a git work-tree root."""
    if not cwd:
        return None
    d = os.path.abspath(cwd)
    while True:
        if os.path.isfile(os.path.join(d, ".pytest_cache", "v", "cache", "lastfailed")):
            return d
        parent = os.path.dirname(d)
        if parent == d or os.path.exists(os.path.join(d, ".git")):
            return None
        d = parent


def failing_nodes(cwd: str) -> list:
    """Every lastfailed node (sorted) that still exists on disk, from the record at
    `record_root(cwd)`; [] on any failure mode — every one is silent.

    A non-empty return is the stale_pass gate's evidence: pytest's own record says each of
    these live nodes was last observed FAILING and has not been re-run green since."""
    root = record_root(cwd)
    if root is None:
        return []
    p = os.path.join(root, ".pytest_cache", "v", "cache", "lastfailed")
    # Same byte cap as every pointed file: a lastfailed past the cap is truncated ->
    # unparseable -> silent (fail-open), never parsed in full. `record_root` already required
    # a regular file, so a FIFO (whose `open()` would hang the Stop hook) is never opened.
    try:
        with open(p, encoding="utf-8") as f:
            data = json.loads(f.read(_MAX_READ_BYTES))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    files: dict = {}
    return [node for node in sorted(k for k, v in data.items() if v is True and isinstance(k, str) and k)
            if _node_exists(root, node, files)]


def stale_failing_node(cwd: str) -> str | None:
    """The FIRST (sorted) live lastfailed node, else None (see `failing_nodes`)."""
    nodes = failing_nodes(cwd)
    return nodes[0] if nodes else None
