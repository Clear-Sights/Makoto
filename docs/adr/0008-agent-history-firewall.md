# 0008: Agent history firewall

Date: 2026-08-16

## Relocated design history

From `run_stop_checks()`:

```text
# Thread-boundary firewall: no Stop gate may linearize another agent's events into this
# agent's call stream. In particular, canon FD14-A must never synthesize a failure from a
# dangling PreToolUse owned by a sibling subagent. Preserved BEFORE narrowing as
# history_all_agents (below) -- gate.claimed_running's Bash-launch evidence deliberately
# pools every thread, a completed PostToolUse row carrying none of the dangling-PreToolUse
# risk this firewall exists to stop (see GateContext.history_all_agents).
```
