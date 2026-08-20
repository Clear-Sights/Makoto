"""makoto.substrate.pytest_cache (L1) — existence-filtered reader over pytest's own on-disk record.

ACCESS CONTRACT (spec §0, Makoto-not-Historia): deterministic direct-pointer I/O ONLY.
This module opens exactly ONE determined file (`<cwd>/.pytest_cache/v/cache/lastfailed`)
and then follows only paths NAMED INSIDE it, scanning each for the node's own concrete
tokens (a line-leading `def <test_name>`, plus `class <Name>` for each class segment).
O(entries), bounded by _MAX_ENTRIES, zero directory enumeration —
no enumeration primitive of any kind, ever (pinned by tests/test_pytest_cache.py).

WHY existence-filtering (the staleness firewall): pytest clears a lastfailed entry only
when it COLLECTS that node and sees it pass — a deleted/renamed node is uncollectable, so
its entry persists forever. MEASURED 2026-06-09 on this repo's green suite: 42/42 stale
entries were exactly that class; the filter (file exists AND `def <name>` present) killed
all 42 with 0 false survivors. A surviving entry therefore means: this node EXISTS and its
last recorded run FAILED, never re-run green — pytest rewrites the cache on every run, so
the record is latest-wins with no makoto bookkeeping. Knight-Leveson: stdlib json/re/os only.
"""
from __future__ import annotations
import json
import os
import re

# Hot-path bounds (literal-lookup latency contract: the WHOLE lookup is a literal
# direct-pointer read and must stay far under ~200-300ms): examine at most _MAX_ENTRIES
# entries (sorted, deterministic) and read at most _MAX_READ_BYTES per pointed file.
# Beyond-cap entries / past-cap bytes are UNEXAMINED -> fail-open (the gate stays
# silent — truncation can only SILENCE, never false-fire), never a crawl.
_MAX_ENTRIES = 50
_MAX_READ_BYTES = 256 * 1024
_NAME_RX = re.compile(r"[A-Za-z_]\w*\Z")


def _node_exists(cwd: str, node: str) -> bool:
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
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read(_MAX_READ_BYTES)
    except OSError:
        return False
    for cls in parts[1:-1]:
        if not _NAME_RX.match(cls):
            return False
        if not re.search(rf"(?m)^[ \t]*class[ \t]+{re.escape(cls)}\b", src):
            return False
    return bool(re.search(rf"(?m)^[ \t]*(?:async[ \t]+)?def[ \t]+{re.escape(name)}\b", src))


def stale_failing_node(cwd: str) -> str | None:
    """The FIRST (sorted) lastfailed node that still exists on disk, else None.

    None on: no cwd, no cache file, unparseable/non-dict JSON, every entry filtered
    (deleted/renamed nodes), or only beyond-cap entries — every failure mode is silent.
    A non-None return is the stale_pass gate's evidence: pytest's own record says this
    live node was last observed FAILING and has not been re-run green since."""
    if not cwd:
        return None
    p = os.path.join(cwd, ".pytest_cache", "v", "cache", "lastfailed")
    # Same regular-file filter and byte cap as every pointed file: `isfile` is False for a
    # FIFO (whose `open()` would hang the Stop hook past its budget), and a lastfailed past
    # the cap is truncated -> unparseable -> silent (fail-open), never parsed in full.
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            data = json.loads(f.read(_MAX_READ_BYTES))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    nodes = sorted(k for k, v in data.items() if v is True and isinstance(k, str) and k)
    for node in nodes[:_MAX_ENTRIES]:
        if _node_exists(cwd, node):
            return node
    return None
