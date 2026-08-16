# 0024: Dunder-insensitive Pre/Post call pairing

## Relocated design history

From `_pairing_input()` in `canonTimeoutRecur.py`:

```text
A harness may add bookkeeping keys to `tool_input` BETWEEN a call's Pre and its Post
(observed live on the `Artifact` tool: a 3-key Pre, then a 6-key Post carrying
`__artifactPlanConsentAsk`, `__artifactPlanConsentDecisionCaps`, `__artifactPublishTarget`).
Pairing on the FULL canonical input therefore never matched those two rows, so every such
call left a dangling Pre and synthesized a phantom mid-turn-abandonment failure — for a call
that in fact succeeded. Two of those back-to-back read as an all-error run of length 2 and
false-fired `canon.recur` STUCK on a retry that had actually succeeded (#17).
```

The current rationale for why the relaxation is sound — a leading `__` is a transport/bookkeeping
convention, never call semantics, and this RELAXES PAIRING ONLY (`recur_stuck`, `identical_retry`
and every other primitive keep keying on the full `_canon_input`) — stays in the source docstring.
