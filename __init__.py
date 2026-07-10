"""makoto package root.

ROOT DOMAIN (2026-07-09, on-the-record per the owner's singular-domain restructuring;
tightened 2026-07-10, bedrock audit): this package root holds ONLY live install/CLI/routing
entry points -- `__init__.py`, `__main__.py`, `_dispatch.py`, `install.py`,
`_dispatch_shim.sh` -- and nothing else. Every installed user's `settings.json` hook wiring
and `_dispatch_shim.sh` reference these exact dotted paths (`makoto._dispatch`,
`makoto.__main__`), so they are frozen: moving any of them into a domain subpackage would
break every existing installation until a fresh `makoto install`. Everything else lives in a
named domain subpackage (`core/`, `substrate/`, `record/`, `verdict/`, `session/`,
`checks/`) -- this is the one deliberate, checkable exception, not a quiet one: the predicate
is "does all of X (entry points) and only X live here," and it is exactly as falsifiable as
any subpackage's own domain rule.

No re-exports (bedrock audit, 2026-07-10): the former `PreCheck`/`Finding` re-export surface
had zero callers anywhere -- every consumer imports `makoto.core.schema` directly, so the
alias path was a second name for the same thing and was cut rather than kept plausible.
"""
