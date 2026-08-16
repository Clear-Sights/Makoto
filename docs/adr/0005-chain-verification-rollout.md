# 0005: Chain verification rollout

Date: 2026-07-07

## Relocated design history

From `_self_verify_chain()`:

```text
Task 2 slice 3 (owner: "Makoto should read its own ledger for verification -- its things
literally depend on it"). Re-derives the chain's own tamper-evidence at every dispatch, the
same every-event cadence Assay's kernel ran. OWNER DECISION (2026-07-07): advisory-first,
block-after-soak -- this ships ADVISORY ONLY (an on-the-record dispatch fact + a stderr line,
never a block) until real-session soak evidence earns the flip to block, itself a later,
separately-certified change. A clean or absent/empty chain is vacuously silent (verify_chain's
own contract). NEVER RAISES: a verification fault must not crash the hot path it protects.
```
