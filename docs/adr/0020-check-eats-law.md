# 0020: Check input-signature law

Date: 2026-08-16

## Relocated design history

From `Check` in `makoto/registry.py`:

```text
`eats` is the check's exact declared input signature. Stop checks name GateContext fields or
derived properties; Pre checks use the flat predicate vocabulary current_event/history/
pattern/conn. tests/test_check_law_eats.py derives the reachable reads and rejects either an
undeclared read or a dead declaration.
```
