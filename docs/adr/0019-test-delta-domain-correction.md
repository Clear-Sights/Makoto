# 0019: Test-delta domain correction

Date: 2026-08-16

## Relocated design history

From `_accumulate()`:

```text
# Task 3, the domain correction (test-delta redirect): compute the delta vs the
# PRIOR recorded testrun BEFORE record_update's upsert overwrites it -- the only
# point where "prior" is still readable. ADVISE-tier (Post has no fire_level
# invariant -- Pre's error-only rule doesn't apply here): a factual diff is always
# safe to surface, never a toothless hedge, so no discrimination problem exists.
```
