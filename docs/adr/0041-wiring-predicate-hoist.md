# 0041: Wiring predicate hoisted to substrate.wiring

Date: 2026-07-09

## Relocated design history

From `selfWiredCheck.py`'s import block:

```text
The 2026-07-09 dedup pass performed exactly the hoist this module's old note asked for: the
wiring predicate now lives in makoto.substrate.wiring (an L0 primitive module, firewall-
allowed by tests/test_import_direction.py's pipeline-order firewall), shared with install.py
instead of mirrored by hand.
```

## Decision

`entry_dispatches_to_makoto` / `event_wired` / `read_plugin_manifest_hooks` live in
`makoto.substrate.wiring` and are imported by both `install.py` and this check.

## Rationale

`substrate.wiring` is an L0 primitive module, so importing it satisfies the pipeline-order
firewall enforced by `tests/test_import_direction.py`. Sharing one implementation keeps the
check's notion of "makoto is wired here" identical to the installer's, rather than a
hand-mirrored copy that can diverge.

## Alternatives considered

Mirroring the predicate by hand in the check (the prior arrangement the old note asked to
replace).
