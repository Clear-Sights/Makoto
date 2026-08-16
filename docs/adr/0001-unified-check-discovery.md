# 0001: Unified check discovery

Date: 2026-08-16

## Relocated design history

From `makoto/registry.py` module documentation:

```text
This module is now the SOLE discovery path for both edges (2026-08-16): `schema.load_prechecks`
has been retired, and `dispatch.py`'s Pre-tier predicate loop, Stop-finding loop, and
`_blocking_gate_ids()` all call `load_checks(edge=...)` directly -- no second catalog, no
schema.py-owned TOML/adapter layer left in the hot path. Stop-edge discovery has run entirely
through this module since 2026-07-10 (the former `load_stopchecks()`/`GATE`-export mechanism,
itself relocated here 2026-07-09 from the deleted `stopchecks/__init__.py` compat shim, was
retired entirely then; every check that used to export a `GATE` now expresses the same Stop-edge
surface as a plain `CHECK` (or an `EXTRA_CHECKS` entry for `contractOrder.py`'s dual Pre+Stop
surface), with `may_block=True` where `GATE`'s presence used to imply blocking-eligibility -- see
`Check.may_block`'s own docstring). `load_precheck_catalog()` (below) is the Pre-tier convenience
wrapper that replaces `schema.load_prechecks()`'s old default-path behavior.
```

From `load_precheck_catalog()`:

```text
inspection commands) consume. Replaces `schema.load_prechecks()`'s old default-path
behavior (retired 2026-08-16): the invariant it used to enforce at load time (every
Pre-tier check must be `posture == BLOCK` -- makoto has no non-blocking Pre tier) is no
longer re-checked here on every hot-path call; it is pinned instead by
`tests/test_pre_tier_block_invariant.py`, which asserts it against this exact catalog.
```

From `_run_predicates()`:

```text
# 2026-08-16: sourced directly from the checks/ catalog via registry --
# schema.load_prechecks() (the TOML/adapter shim) is retired. See
# tests/test_pre_tier_block_invariant.py for the BLOCK-only invariant this used to enforce
# at load time.
```

From `run_stop_checks()`:

```text
# Build the Stop substrate ONCE, then evaluate every live CHECK discovered for the Stop
# edge (2026-07-10: unified via checks._loader.load_checks, retiring the former
# load_stopchecks()-only loop -- this ALSO now naturally includes staleEstablisher and
# undeclaredFalsifiable, formerly special-cased direct-call/never-invoked carve-outs below
# this comment, since neither exported a GATE and load_stopchecks() never discovered them;
# `may_block=False` on both keeps their pattern_id structurally out of
# `_blocking_gate_ids()` regardless of this unification, exactly as before). Each gate
# module owns its own adapter (GateContext -> the gate's heterogeneous signature), so this
# loop never names a gate. gate.dropped resolves against the agent's OWN ledger
# (touched_keys) + cwd-relative fs_exists/fs_read via ctx.roots=[cwd] — NOT an unbounded
# os.walk (a Stop-hot-path landmine). meaning_gate / hidden_retraction were CUT (io-purge
# B3): designs + measured FP evidence live in docs/MAKOTO-BIBLE.md; git history is the
# recovery path.
```
