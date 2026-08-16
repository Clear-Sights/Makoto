# 0002: Stop-check blocking eligibility

Date: 2026-07-10

## Relocated design history

From `Check`:

```text
`may_block` (added when `load_stopchecks()`/`GATE` was retired -- DESIGN DECISION): a Stop-edge
check is blocking-eligible only when BOTH `may_block is True` AND `posture == BLOCK` --
two independent signals, not one. Before this field existed, blocking-eligibility was
`posture == BLOCK` alone; `may_block` restores the second, structural layer the old
`GATE`-export-presence mechanism used to provide (a check with no `GATE` export could
never enter `_blocking_gate_ids()`, regardless of its posture -- see
`staleEstablisher.py`/`undeclaredFalsifiable.py`, which stay `may_block=False` on purpose:
their pattern_id must never enter the blocking-eligible set even if `posture` were ever
mistagged). A Pre-tier CHECK never sets this; it reads back False and is irrelevant there
(`_blocking_gate_ids()` only ever consults Stop-edge checks).
```

From `_blocking_gate_ids()`:

```text
The Stop-gate finding ids eligible to reach `_emit_decision` at all (BLOCK or surfaced
ADVISE) when gates are enabled -- misnamed by history (kept for callers/tests already using
it), but NOT a hand-synced literal: DERIVED from `Check.may_block` via
`checks._loader.load_checks(edge="Stop")` (2026-07-10, retiring the former
`load_stopchecks()`/`GATE`-export mechanism). `may_block=True` marks exactly the checks that
used to export a `GATE` -- every one of them reaches this pipeline regardless of its own
`.level`/posture (the actual BLOCK-vs-ADVISE split happens inside `_emit_decision`/
`_worst_finding`, keyed on each Finding's own `.level`, unchanged by this migration).
`staleEstablisher`/`undeclaredFalsifiable` stay `may_block=False` ON PURPOSE: their
pattern_id must never enter this set at all, a STRUCTURAL exclusion independent of whatever
`.level` their own `run()` might ever compute -- the former GATE-export-presence mechanism
provided the exact same guarantee; this preserves it under the unified loader rather than
collapsing to a single posture-only signal.

Lazy + memoized: the loader imports every checks/*.py module, and Pre/PostToolUse dispatches
(the per-event hot path) never consult this set — as a module-level constant they paid that
import cost on every event. Stop dispatches load the same modules via run_stop_checks
anyway, so laziness changes no Stop behavior.
```
