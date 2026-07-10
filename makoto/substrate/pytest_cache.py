"""lib/pytest_cache.py (L1) — existence-filtered reader over pytest's own on-disk record.

ACCESS CONTRACT (spec §0, Makoto-not-Historia): deterministic direct-pointer I/O ONLY.
This module opens exactly ONE determined file (`<cwd>/.pytest_cache/v/cache/lastfailed`)
and then follows only paths NAMED INSIDE it, scanning each for one concrete token
(`def <test_name>`). O(entries), bounded by _MAX_ENTRIES, zero directory enumeration —
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
    the node carries its own path; for `file::...::name` the FINAL segment (parametrize
    `[...]` id stripped) must appear as a `def <name>` in that file's text. Absolute or
    parent-escaping paths are rejected (cross-project firewall); an unparseable name or
    unreadable file -> False (fail-open: the gate stays silent)."""
    parts = node.split("::")
    rel = parts[0]
    if not rel or os.path.isabs(rel) or rel.startswith("\\") or ".." in rel.split("/"):
        return False
    path = os.path.join(cwd, rel)
    if not os.path.isfile(path):
        return False
    if len(parts) == 1:
        return True                        # module-level entry (collection error) -> file is the node
    name = parts[-1].split("[", 1)[0]
    if not _NAME_RX.match(name):
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read(_MAX_READ_BYTES)
    except OSError:
        return False
    return bool(re.search(rf"\bdef\s+{re.escape(name)}\b", src))


def stale_failing_node(cwd: str):
    """The FIRST (sorted) lastfailed node that still exists on disk, else None.

    None on: no cwd, no cache file, unparseable/non-dict JSON, every entry filtered
    (deleted/renamed nodes), or only beyond-cap entries — every failure mode is silent.
    A non-None return is the stale_pass gate's evidence: pytest's own record says this
    live node was last observed FAILING and has not been re-run green since."""
    if not cwd:
        return None
    p = os.path.join(cwd, ".pytest_cache", "v", "cache", "lastfailed")
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    nodes = sorted(k for k, v in data.items() if v is True and isinstance(k, str) and k)
    for node in nodes[:_MAX_ENTRIES]:
        if _node_exists(cwd, node):
            return node
    return None
