"""The receipt emitter (Task 2 slice 4) -- Makoto blocks the illusory word but, until now,
issued no tender for the kept one; the README promises "trustworthy tender... without
re-deriving it" and nothing emitted it. This closes that gap.

DESIGN DECISION 2026-07-07 (curated brief: claim kinds, shape, persistence):
  1. Only `verdict`/`certified-fact`/`testrun` chain rows count as CLAIMS -- kinds that assert
     something about the world (the ancestor canon/mint.py's "spendable if backed by a real
     deed" test). `audit`/`touched`/`release.operator`/`fetch`/`exemption` are records of deeds and
     machinery, not claims, and folding them in would blur exactly the distinction the receipt
     exists to expose.
  2. One dict per call: {ts, session_id, chain_name, verified_through, claims, claim_count,
     trace_bound_count, exemption_count} -- a list of citations plus PARALLEL counts, never
     combined into one score (HOURGLASS: a measure you optimize for stops measuring). Every
     claim cites its own row_index/row_hash, independently re-checkable against `verify_chain`.
  3. A PURE READ-TIME VIEW -- nothing persisted. A 4th file to keep in sync, or a chain row that
     could only attest to a chain it is itself inside, both cut against this project's own "one
     stream, everything else a view" goal (SPEC-C item 1).

`trace_bound` = at or before `verified_through`'s cut (or every row, if the whole chain is
intact) -- a claim AFTER the first broken link can no longer be trusted to be what it claims to
be, so it is excluded from trace_bound_count (though still listed in `claims`, undisguised).
"""
from __future__ import annotations
from typing import Optional
from pathlib import Path

from makoto.record import ledger
_CLAIM_KINDS = frozenset({"verdict", "certified-fact", "testrun"})
_EXEMPTION_KIND = "exemption"


def _session_matches(row: dict, session_id: Optional[str]) -> bool:
    return session_id is None or row.get("session_id") == session_id


def _trace_bound(row_index: int, verified_through: Optional[int]) -> bool:
    return verified_through is None or row_index < verified_through


def emit_receipt(*, session_id: Optional[str] = None, name: str = "chain",
                 root: Optional[Path] = None) -> dict:
    """Compute one receipt over the chain at `root` (env-var default when None), optionally
    scoped to one `session_id`. Never raises: reads `ledger.read`/`verify_chain`, both of which
    are themselves never-raise (absent/empty chain -> a vacuous, all-zero receipt)."""
    rows = ledger.read(name=name, root=root)
    verified_through = ledger.verify_chain(name=name, root=root)

    claims = [
        {"claim_kind": row.get("kind"), "row_index": idx, "row_hash": row.get("row_hash", "")}
        for idx, row in enumerate(rows)
        if row.get("kind") in _CLAIM_KINDS and _session_matches(row, session_id)
    ]
    trace_bound_count = sum(1 for c in claims if _trace_bound(c["row_index"], verified_through))
    exemption_count = sum(
        1 for idx, row in enumerate(rows)
        if row.get("kind") == _EXEMPTION_KIND and _session_matches(row, session_id)
        and _trace_bound(idx, verified_through)
    )
    return {
        "session_id": session_id,
        "chain_name": name,
        "verified_through": verified_through,
        "claims": claims,
        "claim_count": len(claims),
        "trace_bound_count": trace_bound_count,
        "exemption_count": exemption_count,
    }
