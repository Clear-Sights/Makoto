# 0014: Live plan lifecycle

Date: 2026-07-23

## Relocated design history

From `_accumulate()`:

```text
# SPEC-5 live plan wiring (2026-07-23), two halves of the same gap: DECLARE and ADVANCE.
# Before this, the ONLY way to populate a plan was a `.claude/makoto-plan.jsonl` already
# sitting on disk BEFORE SessionStart fired -- nothing let Claude declare a plan
# mid-session at all -- AND even a SessionStart-declared plan could never CLOSE: Plan.
# mark_done/plan.persist_plan previously had zero live callers, so gate.contract_order's
# Stop remainder would block every subsequent Stop forever once any plan existed
# (contractOrder.py's Pre/Stop sides only ever READ the plan). Both halves key off the
# SAME resolution contractOrder.py's Pre-gap-guard already uses (`_event_location`/
# `Plan.resolve`), imported rather than duplicated -- this orchestrator carries no
# L2-import firewall (contractOrder.py's own docstring scopes that firewall to discovered
# Stop GATE modules, which dispatch.py is not). A no-op when the tool isn't a locating
# one, nothing resolves, or (advance side) no plan is declared.
```
