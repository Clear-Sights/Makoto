# 0009. Render decisions with per-edge wire tables

## Status

Accepted.

## Decision and context

The posture pipeline replaced the old single ad-hoc `{"decision":"block"}` shape that `main()` used identically for every edge. It folds the worst fired outcome through the configured `MAKOTO_MODE` posture and renders it through `verdict.dispatch_posture`'s per-edge table.

A BLOCK carries the finding's message and JIT hint — convention text, `makoto-allow` hatch, and conventions pointer — as the decision detail, the same text `_build_decision` formerly placed in `retry_hint`. An ADVISE or ASK at an edge with no table entry, and the absence of findings, both write nothing, preserving the former no-decision behavior.

`PostToolUse` was missing from the hook-to-edge map until Task 3's test-delta redirect became the first PostToolUse caller of `_emit_decision`. Before that caller existed, the defect was latent: the default-to-Pre fallback would have rendered the wrong edge's wire shape, including `hookEventName="PreToolUse"`, for a PostToolUse response. The explicit Post edge prevents that fallback.

While building the D9 demo corpus, the test-delta redirect exposed a second gap. Its finding rendered correctly on the wire but was invisible to the audit trail and ledger chain, contradicting Task 2's invariant that every dispatch audit row is chain-appended. The redirect therefore records its finding through `_record_audit` as well as emitting it.
