# 0010: PostToolUse wire edge

Date: 2026-08-16

## Relocated design history

From the `_HOOK_TO_EDGE` mapping:

```text
# "PostToolUse" was missing until Task 3's test-delta redirect became the first PostToolUse
# caller of _emit_decision -- previously latent (the .get(..., "Pre") fallback silently rendered
# the WRONG edge's wire shape, with hookEventName="PreToolUse" on a PostToolUse response, had
# anything ever called _emit_decision from the PostToolUse branch before now).
```
