# 0001. Advisory-first ledger self-verification

## Status

Accepted.

## Decision and context

Task 2 slice 3 was owned under the principle that “Makoto should read its own ledger for verification — its things literally depend on it.” Makoto re-derives the chain's own tamper-evidence at every dispatch, at the same every-event cadence Assay's kernel ran.

The owner decision on 2026-07-07 was advisory-first, block-after-soak. This ships advisory only: an on-the-record dispatch fact plus a stderr line, never a block, until real-session soak evidence earns the flip to block. That flip must itself be a later, separately-certified change.

A clean or absent/empty chain is vacuously silent under `verify_chain`'s own contract. Verification never raises: a verification fault must not crash the hot path it protects.
