# 0015: Plan-item event source

Date: 2026-07-10

## Relocated design history

From `_accumulate()`:

```text
# Task #19c (2026-07-10): the harness's own TaskCreate/TaskUpdate calls are the
# GROUND-TRUTH source for the plan-item store the prose sourcer only approximates
# -- an explicit create opens `task:<id>`, an explicit completed/deleted
# transition discharges it, and planItemDrift.py's ADVISORY Stop reminder then
# surfaces anything still open. Same fail-open umbrella as the ledger write.
```
