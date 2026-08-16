# 0006. Wire live plan declaration and advancement

## Status

Accepted.

## Decision and context

The SPEC-5 live plan wiring on 2026-07-23 closed two halves of the same gap: declaration and advancement.

Previously, the only way to populate a plan was for `.claude/makoto-plan.jsonl` to exist before `SessionStart` fired; nothing let Claude declare a plan mid-session. Even a plan declared at SessionStart could never close: `Plan.mark_done` and `plan.persist_plan` had no live callers. Once any plan existed, `gate.contract_order`'s Stop remainder would therefore block every subsequent Stop forever because `contractOrder.py`'s Pre and Stop sides only read the plan.

Both halves use the same resolution contract as `contractOrder.py`'s Pre gap guard, `_event_location` and `Plan.resolve`, imported rather than duplicated. The orchestrator has no L2 import firewall; `contractOrder.py`'s own docstring scopes that firewall to discovered Stop GATE modules, which `dispatch.py` is not.

The wiring is a no-op when the tool is not a locating tool, nothing resolves, or, on the advancement side, no plan is declared. A locating write of the artifact declares or redeclares it live with latest-wins semantics and the same falsifiability gate as `declare_plan`. A locating call at an open node's own `where` marks it done.

Task #19c on 2026-07-10 additionally made the harness's own `TaskCreate` and `TaskUpdate` calls the ground-truth source for the plan-item store that the prose sourcer only approximates. An explicit create opens `task:<id>`; an explicit completed or deleted transition discharges it; `planItemDrift.py`'s advisory Stop reminder surfaces anything still open. It shares the ledger write's fail-open umbrella.
