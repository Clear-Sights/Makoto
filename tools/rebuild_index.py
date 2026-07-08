"""tools/rebuild_index.py -- SPEC-C item 1 (docs/SPEC-C-REMAINING.md): the rebuild PROOF for
sqlite as a derived, disposable index.

SCOPE, STATED PRECISELY (not overclaimed): this rebuilds ONLY the `ledger` sqlite table
(touched/testrun/value rows) from the chain -- the one part of `makoto.db` that IS chain-backed
today (Task 2 routed `record_update`'s writes through the chain, additively, opt-in via an
explicit `root`). The `events`/`commitments`/`plans` tables are NOT chain-backed yet -- no
producer chain-appends full raw hook payloads, declared commitments, or plan state -- and are
OUT OF SCOPE here. Claiming a full `makoto.db` rebuild today would overclaim what the chain
actually contains; item 1's larger end-state (the WHOLE db disposable) needs those three
surfaces chain-backed first, which is its own separate, larger, unaddressed piece of work named
here rather than silently assumed away.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from makoto import ledger as _ledger

_LEDGER_KINDS = frozenset({"touched", "testrun", "value"})


def rebuild_ledger_table_from_chain(conn, *, root: Optional[Path] = None) -> int:
    """Replay every chain-VERIFIED touched/testrun/value row into the sqlite `ledger` table
    (latest-wins, via the SAME `_upsert` `record_update` already uses -- reused, never
    re-derived). Only rows within `verify_chain`'s own verified prefix are replayed -- a row
    after the first broken link is untrusted, never replayed, matching the chain's own contract
    everywhere else it's read. `root=None` is always passed to `_upsert`'s own chain-append
    param, so a rebuild NEVER re-appends to the chain it is reading from. Returns the count of
    rows actually replayed."""
    verified_through = _ledger.verify_chain(root=root)
    rows = _ledger.read(root=root)
    if verified_through is not None:
        rows = rows[:verified_through]
    replayed = 0
    for row in rows:
        kind = row.get("kind")
        if kind not in _LEDGER_KINDS:
            continue
        _ledger._upsert(conn, row.get("key"), kind, row.get("value"), row.get("exit"),
                        row.get("source_event_id"), row.get("session_id"), root=None)
        replayed += 1
    return replayed
