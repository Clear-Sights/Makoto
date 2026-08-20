"""makoto package root.

ROOT DOMAIN (2026-07-09, on-the-record per the owner's singular-domain restructuring;
tightened 2026-07-10, bedrock audit): this root contains the frozen install/CLI/routing entry
points (`__init__.py`, `__main__.py`, `dispatch.py`, `configchange.py`, `install.py`,
`_dispatch_shim.sh`) plus the pipeline modules (`vocab.py`, `registry.py`, `kit.py`,
`context.py`, `verdict.py`, `events.py`). Every installed user's `settings.json` hook wiring
and `_dispatch_shim.sh` reference `makoto.dispatch` and `makoto.__main__`, so those entry points
cannot move into a domain subpackage without a fresh `makoto install`. Domain-owned logic lives
under `core/`, `substrate/`, `state/`, or `checks/`; the exact root membership is pinned by
`tests/test_import_direction.py`.

No re-exports (bedrock audit, 2026-07-10): the former `PreCheck`/`Finding` re-export surface
had zero callers anywhere -- every consumer imports `makoto.vocab` directly, so the
alias path was a second name for the same thing and was cut rather than kept plausible.
"""
