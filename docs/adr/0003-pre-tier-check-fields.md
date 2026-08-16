# 0003: Pre-tier check fields

Date: 2026-07-10

## Relocated design history

From `Check`:

```text
`keywords`/`retry_hint`/`description`/`predicate_module` (SPEC-C item 2, Pre-tier cutover,
backported from public 2026-07-10): additive fields consumed only by `schema.load_prechecks()`'s
loader-backed default path and by the Pre-tier predicates themselves (which read
`pattern.retry_hint`/`pattern.description` directly to build their Finding). A Stop-tier CHECK
never sets them and reads them back as their safe empty defaults. `predicate_module` is
conventionally set to the module's own `__name__` at CHECK-construction time
(self-referential, never a hand-typed/stale dotted string).
```
