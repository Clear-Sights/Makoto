# 0016: Delta finding audit record

Date: 2026-08-16

## Relocated design history

From `_accumulate()`:

```text
# Found while building the D9 demo corpus: without this, the delta redirect's
# own finding was invisible to the audit trail and the chain -- contradicting
# Task 2's "every dispatch audit row is chain-appended" invariant. The redirect
# fired on the wire correctly; it just never left a record of having fired.
```
