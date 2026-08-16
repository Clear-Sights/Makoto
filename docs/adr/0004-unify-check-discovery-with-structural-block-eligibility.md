# 0004. Unify check discovery with structural block eligibility

## Status

Accepted.

## Decision and context

`makoto.registry` is the sole discovery path for every edge. On 2026-08-16, `schema.load_prechecks` was retired. The Pre-tier predicate loop, Stop-finding loop, and `_blocking_gate_ids()` now call `load_checks(edge=...)` directly, leaving no second catalog or `schema.py`-owned TOML/adapter layer in the hot path. `load_precheck_catalog()` is the Pre-tier convenience wrapper replacing `schema.load_prechecks()`'s old default-path behavior.

Stop-edge discovery has run entirely through the registry since 2026-07-10. The former `load_stopchecks()`/`GATE`-export mechanism, relocated here on 2026-07-09 from the deleted `stopchecks/__init__.py` compatibility shim, was then retired entirely. Every check that exported a `GATE` now expresses the same Stop-edge surface as a plain `CHECK`, or as an `EXTRA_CHECKS` entry for `contractOrder.py`'s dual Pre+Stop surface.

`may_block=True` preserves the blocking eligibility that the presence of `GATE` used to imply. A Stop-edge check is blocking-eligible only when both `may_block is True` and `posture == BLOCK`: two independent signals, not one. Before `may_block`, blocking eligibility was `posture == BLOCK` alone; the field restores the structural layer provided by the old export-presence mechanism. A check without a `GATE` could never enter `_blocking_gate_ids()` regardless of posture. Accordingly, `staleEstablisher.py` and `undeclaredFalsifiable.py` deliberately remain `may_block=False`, so their pattern ids cannot enter the blocking-eligible set even if posture is mistagged. Pre-tier checks never set the field; `_blocking_gate_ids()` only consults Stop-edge checks.

Every former gate reaches the pipeline regardless of its finding's own level or posture. The actual BLOCK-versus-ADVISE split remains inside `_emit_decision` and `_worst_finding`, keyed on each `Finding.level`.

The blocking-id derivation is lazy and memoized. The loader imports every `checks/*.py` module, while Pre/PostToolUse dispatches never consult this set; a module-level constant would charge that import cost on every event. Stop dispatches load the same modules through `run_stop_checks` anyway, so laziness changes no Stop behavior.

The additive `keywords`, `retry_hint`, `description`, and `predicate_module` fields were introduced in the SPEC-C item 2 Pre-tier cutover, backported from public on 2026-07-10. They were consumed by `schema.load_prechecks()`'s loader-backed default path and by the Pre-tier predicates, which read `pattern.retry_hint` and `pattern.description` directly to build their findings. Stop-tier checks use their safe empty defaults. `predicate_module` is conventionally the module's own `__name__`, never a hand-typed dotted string.
