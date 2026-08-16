# 0013: PostToolUse accumulation

Date: 2026-08-16

## Relocated design history

From `_accumulate()`:

```text
No predicate evaluation and no block — PostToolUse is for accumulation,
never decision. (SPEC-5 Task 8: citations.capture() removed here — see
makoto/citations.py; refresh_if_stale upstream and record_update below are
separate call sites and stay.)
```
