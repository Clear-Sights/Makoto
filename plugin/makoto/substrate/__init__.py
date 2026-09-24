"""makoto.substrate — the cohesive pool of shared helper modules; siblings may import each other,
per tests/test_import_direction.py's layout order.

Intentionally an EMPTY package init — no imports, no re-exports, no module-level work — so
importing any `makoto.substrate.*` module triggers ZERO package-init side effects. Dispatch pays
this import on every hook event, so it stays free."""
