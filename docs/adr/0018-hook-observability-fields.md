# 0018: Hook observability fields

Date: 2026-08-16

## Relocated design history

From `run_stop_checks()`:

```text
# Additive decode-layer extension (observability-only, no gate reads these yet):
# permission_mode/agent_id/agent_type are confirmed-real top-level hook payload
# fields (Claude Code hooks reference) that dispatch.py never extracted before.
```
