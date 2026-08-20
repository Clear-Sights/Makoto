---
description: List makoto's integrity pattern catalog (read-only)
allowed-tools: Bash(python3 -m makoto pattern list)
disable-model-invocation: true
---

## Makoto pattern catalog

!`python3 -m makoto pattern list`

The above is read-only: every pattern id, fire level, and description. To mute a
noisy pattern, set `MAKOTO_DISABLE_PATTERNS=<id>` in your OWN shell (out-of-band) —
this command never changes makoto's configuration.
