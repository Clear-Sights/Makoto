---
description: Read makoto's results ledger by key (read-only)
argument-hint: "[key]"
arguments: key
allowed-tools: Bash(python3 -m makoto show *)
disable-model-invocation: true
---

## Makoto ledger lookup

!`python3 -m makoto show "$key"`

The above is a read-only inspection of the recorded value for `$key` (e.g. a
normalized file path like `src/auth.py`). It never evaluates predicates, never
fires, and never changes state.
